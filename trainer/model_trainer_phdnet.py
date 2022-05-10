
from torch import nn
import os
from utils.setup.initialization import InitWeights_KaimingUniform
from losses import HeatmapLoss, IntermediateOutputLoss, AdaptiveWingLoss, SigmaLoss
from models.UNet_Classic import UNet
from models.PHD_Net import PHDNet
from visualisation import visualize_heat_pred_coords
import torch
import numpy as np
from time import time
# from dataset import ASPIRELandmarks
from datasets.dataset import ASPIRELandmarks
# import multiprocessing as mp
import ctypes
import copy
from torch.utils.data import DataLoader
from utils.im_utils.heatmap_manipulation import get_coords
from torch.cuda.amp import GradScaler, autocast
import imgaug


from torchvision.transforms import Resize,InterpolationMode

from model_trainer_base import NetworkTrainer
from transforms.generate_labels import PHDNetLabelGenerator

class PHDNetTrainer(NetworkTrainer):
    """ Class for the u-net trainer stuff.
    """

    def __init__(self, model_config= None, output_folder=None, logger=None, profiler=None):
        #Device
        self.device = torch.device("cuda" if torch.cuda.is_available() else "cpu")

        #early stopping

        self.early_stop_patience = 150
        self.epochs_wo_val_improv = 0

        #global config variable
        self.model_config = model_config

        #Trainer variables
        self.perform_validation = model_config.TRAINER.PERFORM_VALIDATION

        self.continue_checkpoint = model_config.MODEL.CHECKPOINT
        self.logger = logger
        self.profiler = profiler
        self.verbose_logging = model_config.OUTPUT.VERBOSE
        self.auto_mixed_precision = model_config.SOLVER.AUTO_MIXED_PRECISION
        self.amp_grad_scaler = None #initialise later 
        self.was_initialized = False
        self.fold= model_config.TRAINER.FOLD
        self.output_folder = output_folder
        self.pin_memory = True

      
        #Dataloader info
        self.data_loader_batch_size = model_config.SOLVER.DATA_LOADER_BATCH_SIZE
        self.num_val_batches_per_epoch = 50
        self.num_batches_per_epoch = model_config.SOLVER.MINI_BATCH_SIZE

        #Training params
        self.max_num_epochs =  model_config.SOLVER.MAX_EPOCHS
        self.initial_lr = 1e-2

        #Sigma for Gaussian heatmaps
        self.regress_sigma = model_config.SOLVER.REGRESS_SIGMA
        self.sigmas = [torch.tensor(x, dtype=float, device=self.device, requires_grad=True) for x in np.repeat(self.model_config.MODEL.GAUSS_SIGMA, len(model_config.DATASET.LANDMARKS))]

        
        #get validaiton params
        if model_config.INFERENCE.EVALUATION_MODE == 'use_input_size' or  model_config.DATASET.ORIGINAL_IMAGE_SIZE == model_config.DATASET.INPUT_SIZE:
            self.use_full_res_coords =False
            self.resize_first = False
        elif model_config.INFERENCE.EVALUATION_MODE == 'scale_heatmap_first':
            self.use_full_res_coords =True
            self.resize_first = True
        elif model_config.INFERENCE.EVALUATION_MODE == 'scale_pred_coords':
            self.use_full_res_coords =True
            self.resize_first = False
        else:
            raise ValueError("value for cg.INFERENCE.EVALUATION_MODE not recognised. Choose from: scale_heatmap_first, scale_pred_coords, use_input_size")

        #Get the coordinate extraction method
        # get_coords_pred = get_coord_function(model=self.)

        #get model config parameters
        self.num_out_heatmaps = len(model_config.DATASET.LANDMARKS)
        self.base_num_features = model_config.MODEL.INIT_FEATURES
        self.min_feature_res = model_config.MODEL.MIN_FEATURE_RESOLUTION
        self.max_features = model_config.MODEL.MAX_FEATURES
        self.input_size = model_config.DATASET.INPUT_SIZE
        self.orginal_im_size = model_config.DATASET.ORIGINAL_IMAGE_SIZE


        #get arch config parameters
        self.num_resolution_layers = UnetTrainer.get_resolution_layers(self.input_size,  self.min_feature_res)
        self.num_input_channels = 1
        self.conv_per_stage = 2
        self.conv_operation = nn.Conv2d
        self.dropout_operation = nn.Dropout2d
        self.normalization_operation = nn.InstanceNorm2d
        self.upsample_operation = nn.ConvTranspose2d
        self.norm_op_kwargs = {'eps': 1e-5, 'affine': True}
        self.dropout_op_kwargs = {'p': 0, 'inplace': True} # don't do dropout
        self.activation_function =  nn.LeakyReLU
        self.activation_kwargs = {'negative_slope': 1e-2, 'inplace': True}
        self.pool_op_kernel_size = [(2,2)] * (self.num_resolution_layers -1)
        self.conv_op_kernel_size = [(3,3)] * self.num_resolution_layers # remember set padding to (F-1)/2 i.e. 1
        self.conv_kwargs = {'stride': 1, 'dilation': 1, 'bias': True, 'padding': 1}

        #scheduler, initialiser and optimiser params
        self.weight_inititialiser = InitWeights_KaimingUniform(self.activation_kwargs['negative_slope'])
        self.optimizer= torch.optim.SGD
        self.optimizer_kwargs =  {"lr": self.initial_lr, "momentum": 0.99, "weight_decay": 3e-5, "nesterov": True}

        #Deep supervision args
        self.deep_supervision= model_config.SOLVER.DEEP_SUPERVISION
        self.num_res_supervision = model_config.SOLVER.NUM_RES_SUPERVISIONS

        if not self.deep_supervision:
            self.num_res_supervision = 1 #just incase not set in config properly


        #Loss params
        self.loss_str = model_config.SOLVER.LOSS_FUNCTION
        if self.loss_str == "patch_disp_gauss":
            # self.individual_hm_loss = HeatmapLoss()
            # raise NotImplementedError()
            print("loss not imp yet")
        else:
            raise ValueError("the loss function %s is not implemented. Try patch_disp_gauss" % (self.loss_str))

      

        self.label_generator = PHDNetLabelGenerator()


        ################# Settings for saving checkpoints ##################################
        self.save_every = 25
        self.save_latest_only = model_config.TRAINER.SAVE_LATEST_ONLY  # if false it will not store/overwrite _latest but separate files each
        # time an intermediate checkpoint is created
        self.save_intermediate_checkpoints = True  # whether or not to save checkpoint_latest
        self.save_best_checkpoint = True  # whether or not to save the best checkpoint according to self.best_val_eval_criterion_MA
        self.save_final_checkpoint = True  # whether or not to save the final checkpoint

        #variables to save to.
        self.all_tr_losses = []
        self.all_valid_losses = []
        self.all_valid_coords = []

        #Initialize
        self.epoch = 0
        self.best_valid_loss = 999999999999999999999999999
        self.best_valid_coord_error = 999999999999999999999999999
        self.best_valid_epoch = 0


    def initialize(self, training_bool=True):

        # torch.backends.cudnn.benchmark = True

        if self.profiler:
            print("Initialized profiler")
            self.profiler.start()
        
        if self.logger:
            self.logger.log_parameters(self.model_config)
            
        if training_bool:
            self.set_training_dataloaders()

        self.initialize_network()
        self.initialize_optimizer_and_scheduler()
        self.initialize_loss_function()
        self._maybe_init_amp()
        self.was_initialized = True

        self.maybe_load_checkpoint() 


    def initialize_network(self):

        # Let's make the network
        self.network = PHDNet(self.loss_str)
        self.network.to(self.device)

        #Log network and initial weights
        if self.logger:
            self.logger.set_model_graph(str(self.network))
            print("Logged the model graph.")

     
        print("Initialized network architecture. #parameters: ", sum(p.numel() for p in self.network .parameters()))

    def initialize_optimizer_and_scheduler(self):
        assert self.network is not None, "self.initialize_network must be called first"

      
        self.learnable_params = list(self.network.parameters())
        if self.regress_sigma:
            for sig in self.sigmas:
                self.learnable_params.append(sig)

        self.optimizer = self.optimizer(self.learnable_params, **self.optimizer_kwargs)

   
        print("Initialised optimizer.")


    def initialize_loss_function(self):

        if self.deep_supervision:
            #first get weights for the layers. We don't care about the first two decoding levels
            #[::-1] because we don't use bottleneck layer. reverse bc the high res ones are important
            loss_weights = np.array([1 / (2 ** i) for i in range(self.num_res_supervision)])[::-1] 
            loss_weights = (loss_weights / loss_weights.sum()) #Normalise to add to 1
        else:
            loss_weights = [1]

        if self.regress_sigma:
            self.loss = IntermediateOutputLoss(self.individual_hm_loss, loss_weights,sigma_loss=True, sigma_weight=self.model_config.SOLVER.REGRESS_SIGMA_LOSS_WEIGHT )
        else:
            self.loss = IntermediateOutputLoss(self.individual_hm_loss, loss_weights,sigma_loss=False )

   

        print("initialized Loss function.")

    def maybe_update_lr(self, epoch=None, exponent=0.9):
        """
        if epoch is not None we overwrite epoch. Else we use epoch = self.epoch + 1

        (maybe_update_lr is called in on_epoch_end which is called before epoch is incremented.
        Therefore we need to do +1 here)

        """
        if epoch is None:
            ep = self.epoch + 1
        else:
            ep = epoch
        poly_lr_update = self.initial_lr * (1 - ep / self.max_num_epochs)**exponent

        self.optimizer.param_groups[0]['lr'] =poly_lr_update

    def _maybe_init_amp(self):
        if self.auto_mixed_precision and self.amp_grad_scaler is None:
            self.amp_grad_scaler = GradScaler()
        print("initialized auto mixed precision.")


    def train(self):
        step = 0
        while self.epoch < self.max_num_epochs:
            

            self.epoch_start_time = time()
            train_losses_epoch = []

            self.network.train()

            generator = iter(self.train_dataloader)


            # Train for X number of batches per epoch e.g. 250
            for iter_b in range(self.num_batches_per_epoch):

                l, generator = self.run_iteration(generator, self.train_dataloader, backprop=True)

                train_losses_epoch.append(l)

                if self.logger:
                    self.logger.log_metric("training loss iteration", l, step)

                step += 1

            del generator
            self.all_tr_losses.append(np.mean(train_losses_epoch))

            #Validate
            print("val")
            
            with torch.no_grad():

                self.network.eval()
               

                val_coord_errors = []
                val_losses_epoch = []
                generator = iter(self.valid_dataloader)
                for iter_b in range(int(len(self.valid_dataloader.dataset)/self.model_config.SOLVER.DATA_LOADER_BATCH_SIZE)):

                    l, generator = self.run_iteration(generator, self.valid_dataloader, False, True, val_coord_errors)
                    val_losses_epoch.append(l)
                 

                self.all_valid_losses.append(np.mean(val_losses_epoch)) #go through all valid at once here
                self.all_valid_coords.append(np.mean(val_coord_errors))
            self.epoch_end_time = time()
            print("Epoch: ", self.epoch, " - train loss: ", np.mean(train_losses_epoch), " - val loss: ", self.all_valid_losses[-1], " - val coord error: ", self.all_valid_coords[-1], " -time: ",(self.epoch_end_time - self.epoch_start_time) )
            print("sigmas: ", self.sigmas)

            # print("validation: ", time()-s)
            continue_training = self.on_epoch_end()

            # print("on epoch end:  ", time()-self.epoch_end_time)
            if not continue_training:
                if self.profiler:
                    self.profiler.stop()

                break
     
            self.epoch +=1

        #Save the final weights
        if self.logger:
            print("Logging weights as histogram...")
            weights = []
            for name in self.network.named_parameters():
                if 'weight' in name[0]:
                    weights.extend(name[1].detach().cpu().numpy().tolist())
            self.logger.log_histogram_3d(weights, step=self.epoch)




    def predict_heatmaps_and_coordinates(self, data_dict,  return_all_layers = False, resize_to_og=False,):
        data =(data_dict['image']).to( self.device )
        target = [x.to(self.device) for x in data_dict['label']]
        from_which_level_supervision = self.num_res_supervision 

        if self.deep_supervision:
            output = self.network(data)[-from_which_level_supervision:]
        else:
            output = self.network(data)

        
        l = self.loss(output, target, self.sigmas)

        final_heatmap = output[-1]
        if resize_to_og:
            #torch resize does HxW so need to flip the dimesions for resize
            final_heatmap = Resize(self.orginal_im_size[::-1], interpolation=  InterpolationMode.BICUBIC)(final_heatmap)

        predicted_coords = get_coords(final_heatmap)

        heatmaps_return = output
        if not return_all_layers:
            heatmaps_return = output[-1] #only want final layer


        return heatmaps_return, final_heatmap, predicted_coords, l.detach().cpu().numpy()


    def run_iteration(self, generator, dataloader, backprop, get_coord_error=False, coord_error_list=None):
        so = time()
        try:
            data_dict = next(generator)
        except StopIteration:
            # restart the generator if the previous generator is exhausted.
            print("restarting generator")
            generator = iter(dataloader)
            data_dict = next(generator)


        data =(data_dict['image']).to( self.device )

        target = [x.to(self.device) for x in data_dict['label']]
       
        self.optimizer.zero_grad()
        from_which_level_supervision = self.num_res_supervision 


        if self.auto_mixed_precision:
            with autocast():
                if self.deep_supervision:
                    output = self.network(data)[-from_which_level_supervision:]                
                else:
                    output = self.network(data)
                so = time()
                del data
                l = self.loss(output, target, self.sigmas)
            if backprop:
                self.amp_grad_scaler.scale(l).backward()
                self.amp_grad_scaler.unscale_(self.optimizer)
                torch.nn.utils.clip_grad_norm_(self.learnable_params, 12)
                self.amp_grad_scaler.step(self.optimizer)
                self.amp_grad_scaler.update()
                if self.regress_sigma:
                    self.update_dataloader_sigmas(self.sigmas)

        else:
            if self.deep_supervision:
                output = self.network(data)[-from_which_level_supervision:]
            else:
                output = self.network(data)


            del data
            l = self.loss(output, target, self.sigmas)
        
            if backprop:
                l.backward()
                torch.nn.utils.clip_grad_norm_(self.learnable_params, 12)
                self.optimizer.step() 
                if self.regress_sigma:
                    self.update_dataloader_sigmas(self.sigmas)


        if get_coord_error:
            with torch.no_grad():
                final_heatmap = output[-1]
                if self.resize_first:
                    #torch resize does HxW so need to flip the diemsions
                    final_heatmap = Resize(self.orginal_im_size[::-1], interpolation=  InterpolationMode.BICUBIC)(final_heatmap)
                pred_coords = get_coords(final_heatmap)
                del final_heatmap
               
                if self.use_full_res_coords:
                    target_coords =data_dict['full_res_coords'].to( self.device )
                else:
                    target_coords =data_dict['target_coords'].to( self.device )


                if self.use_full_res_coords and not self.resize_first :
                    downscale_factor = [self.model_config.DATASET.ORIGINAL_IMAGE_SIZE[0]/self.model_config.DATASET.INPUT_SIZE[0], self.model_config.DATASET.ORIGINAL_IMAGE_SIZE[1]/self.model_config.DATASET.INPUT_SIZE[1]]
                    pred_coords = torch.rint(pred_coords * downscale_factor)

                coord_error = torch.linalg.norm((pred_coords- target_coords), axis=2)
                coord_error_list.append(np.mean(coord_error.detach().cpu().numpy()))

       

        if self.profiler:
            self.profiler.step()

        del output
        del target
        return l.detach().cpu().numpy(), generator


    def on_epoch_end(self):
        """
         Always run to 1000 epochs
        :return:
        """

        new_best_valid = False
        new_best_coord_valid = False

        continue_training = self.epoch < self.max_num_epochs

        if self.all_valid_losses[-1] < self.best_valid_loss:
            self.best_valid_loss = self.all_valid_losses[-1]
            self.best_valid_epoch = self.epoch
            new_best_valid = True

        if self.all_valid_coords[-1] < self.best_valid_coord_error:
            self.best_valid_coord_error = self.all_valid_coords[-1]
            self.best_valid_coords_epoch = self.epoch
            new_best_coord_valid = True
            self.epochs_wo_val_improv = 0
        else:
            self.epochs_wo_val_improv += 1


            
        if self.epochs_wo_val_improv == self.early_stop_patience:
            continue_training = False
            print("EARLY STOPPING. Validation Coord Error did not reduce for %s epochs. " % self.early_stop_patience)

        self.maybe_save_checkpoint(new_best_valid, new_best_coord_valid)

        self.maybe_update_lr(epoch=self.epoch)

        # if self.regress_sigma:
        #     self.update_dataloader_sigmas(self.sigmas)

        if self.logger:
            self.logger.log_metric("training loss epoch", self.all_tr_losses[-1], self.epoch)
            self.logger.log_metric("validation loss", self.all_valid_losses[-1], self.epoch)
            self.logger.log_metric("validation coord error", self.all_valid_coords[-1], self.epoch)
            self.logger.log_metric("epoch time", (self.epoch_end_time - self.epoch_start_time), self.epoch)
            self.logger.log_metric("Learning rate", self.optimizer.param_groups[0]['lr'] , self.epoch)
            self.logger.log_metric("first_sigma", self.sigmas[0].cpu().detach().numpy() , self.epoch)

        
       
        return continue_training


    def maybe_save_checkpoint(self, new_best_valid_bool, new_best_valid_coord_bool):
        """
        Saves a checkpoint every save_ever epochs.
        :return:
        """

        fold_str = str(self.model_config.TRAINER.FOLD)
        if (self.save_intermediate_checkpoints and (self.epoch % self.save_every == (self.save_every - 1))) or self.epoch== self.max_num_epochs-1:
            print("saving scheduled checkpoint file...")
            if not self.save_latest_only:
                self.save_checkpoint(os.path.join(self.output_folder, "model_ep_"+ str(self.epoch) + "_fold" + fold_str+ ".model" % ()))
            
                if self.epoch >=150:
                    self.save_every = 50
                if self.epoch >=250:
                    self.save_every = 100
            self.save_checkpoint(os.path.join(self.output_folder, "model_latest_fold"+ (fold_str) +".model"))
            print("done")
        if new_best_valid_bool:
            print("saving scheduled checkpoint file as it's new best on validation set...")
            self.save_checkpoint(os.path.join(self.output_folder, "model_best_valid_loss_fold" + fold_str +".model"))

            print("done")

        if new_best_valid_coord_bool:
            print("saving scheduled checkpoint file as it's new best on validation set for coord error...")
            self.save_checkpoint(os.path.join(self.output_folder, "model_best_valid_coord_error_fold" + fold_str +".model"))

            print("done")

           






    def save_checkpoint(self, path):
        state = {
            'epoch': self.epoch + 1,
            'state_dict': self.network.state_dict(),
            'optimizer' : self.optimizer.state_dict(),
            'best_valid_loss': self.best_valid_loss,
            'best_valid_coord_error': self.best_valid_coord_error,
            'best_valid_epoch': self.best_valid_epoch,
            "best_valid_coords_epoch": self.best_valid_coords_epoch

        }
        if self.amp_grad_scaler is not None:
            state['amp_grad_scaler'] = self.amp_grad_scaler.state_dict()

        torch.save(state, path)


    def maybe_load_checkpoint(self):
        if self.continue_checkpoint:
            self.load_checkpoint(self.continue_checkpoint, True)
    
    def update_dataloader_sigmas(self, new_sigmas):
        np_sigmas = [x.cpu().detach().numpy() for x in new_sigmas]
        self.train_dataloader.dataset.sigmas = (np_sigmas)
        self.valid_dataloader.dataset.sigmas = (np_sigmas)



    def load_checkpoint(self, model_path, training_bool):
        if not self.was_initialized:
            self.initialize(training_bool)

        checkpoint_info = torch.load(model_path, map_location=self.device)
        self.epoch = checkpoint_info['epoch']
        self.network.load_state_dict(checkpoint_info["state_dict"])
        self.optimizer.load_state_dict(checkpoint_info["optimizer"])
        self.best_valid_loss = checkpoint_info['best_valid_loss']
        self.best_valid_epoch = checkpoint_info['best_valid_epoch']
        self.best_valid_coord_error = checkpoint_info['best_valid_coord_error']
        # self.best_valid_coords_epoch = checkpoint_info["best_valid_coords_epoch"]

        if self.auto_mixed_precision:
            self._maybe_init_amp()

            if 'amp_grad_scaler' in checkpoint_info.keys():
                self.amp_grad_scaler.load_state_dict(checkpoint_info['amp_grad_scaler'])

        print("Loaded checkpoint %s. Epoch: %s, " % (model_path, self.epoch ))

    def set_training_dataloaders(self):
        super(PHDNetTrainer, self).set_training_dataloaders()

       
