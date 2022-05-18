
from torch import nn
import os
from utils.setup.initialization import InitWeights_KaimingUniform
from losses import HeatmapLoss, IntermediateOutputLoss, AdaptiveWingLoss, SigmaLoss
from models.PHD_Net import PHDNet
import torch
import numpy as np
from utils.im_utils.heatmap_manipulation import get_coords
import matplotlib.pyplot as plt

# torch.multiprocessing.set_start_method('spawn')# good solution !!!!
from torchvision.transforms import Resize,InterpolationMode
from trainer.model_trainer_base import NetworkTrainer

from transforms.generate_labels import PHDNetLabelGenerator


#TODO: 1) write the label generator for PHDNetLabelGenerator
    # 2) write the loss function for phdnet 
    # 3) write get_coords_from_heatmap (may be the same as unet, in which case put in base)
    #4 ) write predict_heatmaps_and_coordinates from datadict directly
class PHDNetTrainer(NetworkTrainer):
    """ Class for the phdnet trainer stuff.
    """

    def __init__(self, trainer_config= None, is_train=True, output_folder=None, comet_logger=None, profiler=None):


        super(PHDNetTrainer, self).__init__(trainer_config, is_train, output_folder, comet_logger, profiler)

      
        #global config variable
        self.trainer_config = trainer_config


        #Label generator
        self.label_generator = PHDNetLabelGenerator()

        #get model config parameters
        self.num_out_heatmaps = len(self.trainer_config.DATASET.LANDMARKS)
        self.base_num_features = self.trainer_config.MODEL.UNET.INIT_FEATURES
        self.min_feature_res = self.trainer_config.MODEL.UNET.MIN_FEATURE_RESOLUTION
        self.max_features = self.trainer_config.MODEL.UNET.MAX_FEATURES
        self.input_size = self.trainer_config.SAMPLER.INPUT_SIZE
        self.orginal_im_size = self.trainer_config.DATASET.ORIGINAL_IMAGE_SIZE


        #get arch config parameters
        

        #scheduler, initialiser and optimiser params
        self.weight_inititialiser = InitWeights_KaimingUniform(self.activation_kwargs['negative_slope'])
        self.optimizer= torch.optim.SGD
        self.optimizer_kwargs =  {"lr": self.initial_lr, "momentum": 0.99, "weight_decay": 3e-5, "nesterov": True}


        #Loss params
        loss_str = self.trainer_config.SOLVER.LOSS_FUNCTION
        if loss_str == "mse":
            self.individual_hm_loss = HeatmapLoss()
        elif loss_str =="awl":
            self.individual_hm_loss = AdaptiveWingLoss(hm_lambda_scale=self.model_config.MODEL.HM_LAMBDA_SCALE)
        else:
            raise ValueError("the loss function %s is not implemented. Try mse or awl" % (loss_str))



        ################# Settings for saving checkpoints ##################################
        self.save_every = 25






    def initialize_network(self):

        # Let's make the network
        self.network = PHDNet(self.branch_scheme)
        self.network.to(self.device)

        #Log network and initial weights
        if self.comet_logger:
            self.comet_logger.set_model_graph(str(self.network))
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
            self.loss = IntermediateOutputLoss(self.individual_hm_loss, loss_weights,sigma_loss=True, sigma_weight=self.trainer_config.SOLVER.REGRESS_SIGMA_LOSS_WEIGHT )
        else:
            self.loss = IntermediateOutputLoss(self.individual_hm_loss, loss_weights,sigma_loss=False )

        print("initialized Loss function.")




    def get_coords_from_heatmap(self, output):
        """ Gets x,y coordinates from a model output. Here we use the final layer prediction of the U-Net,
            maybe resize and get coords as the peak pixel. Also return value of peak pixel.

        Args:
            output: model output - a stack of heatmaps

        Returns:
            [int, int]: predicted coordinates
        """

        extra_info = {"hm_max": []}

        #Get only the full resolution heatmap
        output = output[-1]

        final_heatmap = output
        if self.resize_first:
            #torch resize does HxW so need to flip the diemsions
            final_heatmap = Resize(self.orginal_im_size[::-1], interpolation=  InterpolationMode.BICUBIC)(final_heatmap)
        
        pred_coords, max_values = get_coords(final_heatmap)
        extra_info["hm_max"] = (max_values)

        del final_heatmap
        

        return pred_coords, extra_info

  
    def stitch_heatmap(self, patch_predictions, stitching_info, gauss_strength=0.5):
        '''
        Use model outputs from a patchified image to stitch together a full resolution heatmap
        
        '''


        full_heatmap = np.zeros((self.orginal_im_size[1], self.orginal_im_size[0]))
        patch_size_x = patch_predictions[0].shape[0]
        patch_size_y = patch_predictions[0].shape[1]

        for idx, patch in enumerate(patch_predictions):
            full_heatmap[stitching_info[idx][1]:stitching_info[idx][1]+patch_size_y, stitching_info[idx][0]:stitching_info[idx][0]+patch_size_x] += patch.detach.cpu().numpy()

        plt.imshow(full_heatmap)
        plt.show()



        

    def predict_heatmaps_and_coordinates(self, data_dict,  return_all_layers = False, resize_to_og=False,):
        data =(data_dict['image']).to( self.device )
        target = [x.to(self.device) for x in data_dict['label']]
        from_which_level_supervision = self.num_res_supervision 

        if self.deep_supervision:
            output = self.network(data)[-from_which_level_supervision:]
        else:
            output = self.network(data)

        
        l, loss_dict = self.loss(output, target, self.sigmas)

        final_heatmap = output[-1]
        if resize_to_og:
            #torch resize does HxW so need to flip the dimesions for resize
            final_heatmap = Resize(self.orginal_im_size[::-1], interpolation=  InterpolationMode.BICUBIC)(final_heatmap)

        predicted_coords, max_values = get_coords(final_heatmap)

        heatmaps_return = output
        if not return_all_layers:
            heatmaps_return = output[-1] #only want final layer


        return heatmaps_return, final_heatmap, predicted_coords, l.detach().cpu().numpy()

    

    def set_training_dataloaders(self):
        super(PHDNetTrainer, self).set_training_dataloaders()





