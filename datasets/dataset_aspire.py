from abc import abstractclassmethod
import os
from pathlib import Path
from typing import List
import warnings

import imgaug as ia
import imgaug.augmenters as iaa
import nibabel as nib
import numpy as np
import torch
from imgaug.augmentables import Keypoint, KeypointsOnImage
from PIL import Image
from torch.utils import data
from torchvision import transforms
from transforms.transformations import (HeatmapsToTensor, NormalizeZScore, ToTensor,
                             normalize_cmr)
from transforms.dataloader_transforms import get_aug_package_loader

from transforms.generate_labels import LabelGenerator, generate_heatmaps
from load_data import get_datatype_load, load_aspire_datalist
from visualisation import (visualize_heat_pred_coords, visualize_image_target,
                           visualize_image_trans_coords,
                           visualize_image_trans_target, visualize_patch, visualize_image_all_coords)
from time import time

import multiprocessing as mp
import ctypes
# import albumentations as A
# import albumentations.augmentations.functional as F
# from albumentations.pytorch import ToTensorV2

from abc import ABC, abstractmethod, ABCMeta

from datasets.dataset_generic import DatasetBase
# class DatasetMeta(data.Dataset):
#    pass

class DatasetAspire(DatasetBase):
    """
    A custom dataset superclass for loading landmark localization data

    Args:
        name (str): Dataset name.
        split (str): Data split type (train, valid or test).
        image_path (str): local directory of image path (default: "./data").
        annotation_path (str): local directory to file path with annotations.
        annotation_set (str): which set of annotations to use [junior, senior, challenge] (default: "junior")
        image_modality (str): Modality of image (default: "CMRI").


    References:
        #TO DO
    """


    #Additional sample attributes we want to log for each sample in the dataset, these are accessable without instantiating the class.
    additional_sample_attribute_keys = ["patient_id", "suid"]

    def __init__(
        self, **kwargs
        ):
        
 
        # super(DatasetBase, self).__init__()
        super(DatasetAspire, self).__init__(**kwargs, additional_sample_attribute_keys=DatasetAspire.additional_sample_attribute_keys)

        #adding specialised sample attributes here
        # self.additional_sample_attributes = dict.fromkeys(DatasetAspire.additional_sample_attribute_keys, [])
        
        # # {"patient_id": [], "suid":[]}
        # print("empty add att dict: ", self.additional_sample_attributes)

    # def add_additional_sample_attributes(self, data):   
    #     #Extended dataset class can add more attributes to each sample here

    #     for k_ in DatasetAspire.additional_sample_attribute_keys:
    #         self.additional_sample_attributes[k_].append(data[k_])
        # print(self.additional_sample_attributes)

        # self.additional_sample_attributes["patient_id"].append(data["patient_id"])
        # self.additional_sample_attributes["suid"].append(data["suid"])
        # return data