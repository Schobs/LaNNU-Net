import imgaug.augmenters as iaa

import albumentations as A
import albumentations.augmentations.functional as F
from albumentations.pytorch import ToTensorV2

def get_aug_package_loader(aug_package):
    """ returns a fucntion to load data augmentations from a given pakage.

    Args:
        aug_package (str): the image augmentation package to use.

    Raises:
        ValueError: if an unsupported package is given by the user.

    Returns:
        function: function to load data augmentation for the given package.
    """

    if aug_package == "imgaug":
        return get_imgaug_transforms
    elif aug_package == "albumentations":
        return get_albumentation_transforms
    else:
        raise ValueError("aug package %s not supported. Try \"imgaug\" or  \"albumentations\" " % (aug_package))


def get_imgaug_transforms(data_augmentation, final_im_size):
    """ Returns a data augmentation sequence from the imgaug package

    Args:
        data_augmentation (str): name of the data augmentation strategy

    Raises:
        ValueError: error if data_augmentation has not been defined as a strategy

    Returns:
        transform: sequence of transforms
    """
    if data_augmentation =="AffineSimple":

        transform = iaa.Sequential([
            iaa.Sometimes(
                0.75,
                iaa.Affine(
                    rotate=(-45,45),
                    scale=(0.8, 1.2),
                ),
            ),
            iaa.flip.Flipud(p=0.5),
            iaa.CenterCropToFixedSize(final_im_size[0], final_im_size[1])

        ])

    elif data_augmentation == "TTA":
      transform = iaa.Sequential([
            iaa.Sometimes(
                0.6,
                iaa.TranslateY(px=(-10, 10)),
                iaa.TranslateX(px=(-10, 10)),
            ),
            iaa.flip.Flipud(p=0.5),
            iaa.flip.Fliplr(p=0.5),
        ])

    elif data_augmentation =="AffineComplex":
        transform = iaa.Sequential([
            iaa.Sometimes(
                0.5,
                iaa.Affine(
                    scale={"x": (0.8, 1.2), "y": (0.8, 1.2)},
                    translate_percent={"x": (-0.07, 0.07), "y": (-0.07, 0.07)},
                    rotate=(-45, 45),
                    shear=(-16, 16),
                    order=[0, 1],
                )
            ),
            iaa.flip.Flipud(p=0.5),
            iaa.CenterCropToFixedSize(final_im_size[0], final_im_size[1])
        ])
    elif data_augmentation == "AffineComplexElastic":
        transform = iaa.Sequential([
            iaa.Sometimes(
                0.5,
                iaa.Affine(
                    scale={"x": (0.8, 1.2), "y": (0.8, 1.2)},
                    translate_percent={"x": (-0.07, 0.07), "y": (-0.07, 0.07)},
                    rotate=(-45, 45),
                    shear=(-16, 16),
                    order=[0, 1],
                )
            ),
            iaa.flip.Flipud(p=0.5),
            iaa.Sometimes(
                0.5,
                iaa.ElasticTransformation(alpha=(0,200), sigma=(9,13))
            ),
            iaa.CenterCropToFixedSize(final_im_size[0], final_im_size[1])

        ])
    elif data_augmentation == "AffineComplexElasticLight":
        transform = iaa.Sequential([
            iaa.Sometimes(
                0.5,
                iaa.Affine(
                    scale={"x": (0.8, 1.2), "y": (0.8, 1.2)},
                    translate_percent={"x": (-0.07, 0.07), "y": (-0.07, 0.07)},
                    rotate=(-45, 45),
                    shear=(-16, 16),
                    order=[0, 1],
                )
            ),
            iaa.flip.Flipud(p=0.5),
            iaa.Sometimes(
                0.5,
                iaa.ElasticTransformation(alpha=(0,50), sigma=(5,10))
            ),
            iaa.CenterCropToFixedSize(final_im_size[0], final_im_size[1])

        ])
    elif data_augmentation == "AffineComplexElasticBlur":
        transform = iaa.Sequential([
            iaa.Sometimes(
                0.5,
                iaa.Affine(
                    scale={"x": (0.8, 1.2), "y": (0.8, 1.2)},
                    translate_percent={"x": (-0.07, 0.07), "y": (-0.07, 0.07)},
                    rotate=(-45, 45),
                    shear=(-16, 16),
                    order=[0, 1],
                )
            ),
            iaa.flip.Flipud(p=0.5),
            iaa.Sometimes(
                0.5,
                iaa.ElasticTransformation(alpha=(0, 50), sigma=(2,5))
            ),

            iaa.Sometimes(
                0.5,
                iaa.OneOf([
                    iaa.GaussianBlur((0, 0.2)),
                    iaa.AverageBlur(k=(3, 5)),
                    iaa.MedianBlur(k=(3, 5)),
                    iaa.AveragePooling(2)
                ])
            ),
            iaa.CenterCropToFixedSize(final_im_size[0], final_im_size[1])

        ])
    elif data_augmentation == "AffineComplexElasticBlurSharp":
        transform = iaa.Sequential([
            iaa.Sometimes(
                0.5,
                iaa.Affine(
                    scale={"x": (0.8, 1.2), "y": (0.8, 1.2)},
                    translate_percent={"x": (-0.07, 0.07), "y": (-0.07, 0.07)},
                    rotate=(-45, 45),
                    shear=(-16, 16),
                    order=[0, 1],
                )
            ),
            iaa.flip.Flipud(p=0.5),
            iaa.Sometimes(
                0.5,
                iaa.ElasticTransformation(alpha=(0, 50), sigma=(2,5))
            ),

            iaa.Sometimes(
                0.5,
                iaa.OneOf([
                    iaa.GaussianBlur((0, 0.2)),
                    iaa.AverageBlur(k=(3, 5)),
                    iaa.MedianBlur(k=(3, 5)),
                    iaa.AveragePooling(2)
                ])
            ),
            iaa.Sometimes(
                0.5,
                iaa.SomeOf(
                    (0,3), 
                    [
                        iaa.Sharpen(alpha=(0, 0.75), lightness=(0, 0.5)),
                        iaa.Emboss(alpha=(0, 0.5), strength=(0, 1)),
                        iaa.LinearContrast((0.4, 1.6))                            
                    ]
                )
            ),
            iaa.CenterCropToFixedSize(final_im_size[0], final_im_size[1])

        ])
    elif data_augmentation =="payer19":
        transform = iaa.Sequential([
            iaa.Affine(
                translate_px=(-20,20),
                rotate=(-15,15),
                scale=(0.6,1.4),

            ),
            iaa.ElasticTransformation(alpha=(0, 50), sigma=(2,5)),
            iaa.AddElementwise((-0.25, 0.25)),
            iaa.MultiplyElementwise((0.75, 1.25)),
            iaa.CenterCropToFixedSize(final_im_size[0], final_im_size[1])

            
        ])

    elif data_augmentation =="thaler21":
        transform = iaa.Sequential([
            iaa.Affine(
                translate_px=(-10,10),
                rotate=(-15,15),
                scale=(0.8,1.2),

            ),
            iaa.Affine(
                scale={"x": (0.8, 1.2), "y": (0.8, 1.2)},
            ),
            iaa.ElasticTransformation(alpha=(0, 50), sigma=(2,5)),

            iaa.AddElementwise((-0.25, 0.25)),

            iaa.MultiplyElementwise((0.75, 1.25)),
            iaa.CenterCropToFixedSize(final_im_size[0], final_im_size[1])

            
        ])
    elif data_augmentation == "CenterCropOnly":
        transform = iaa.Sequential([
            iaa.CenterCropToFixedSize(final_im_size[0], final_im_size[1])
        ])


    else:
        raise ValueError("transformations mode for dataaugmentation not recognised.")
    

    return transform

def get_albumentation_transforms(data_augmentation):
    """ Returns a data augmentation sequence from the albumentation package

    Args:
        data_augmentation (str): name of the data augmentation strategy

    Raises:
        ValueError: error if data_augmentation has not been defined as a strategy

    Returns:
        transform: sequence of transforms
    """
    if data_augmentation == "V1":
        transform = A.Compose(
            [
                # A.AdvancedBlur(),
                # A.CLAHE(),
                # A.HueSaturationValue(),
                # A.RandomBrightnessContrast(),
                # A.RandomGamma(),
                # A.GaussNoise(),
                # A.CoarseDropout(),
                # A.Downscale(),
                # A.ElasticTransform(),
                A.Flip(),
                A.SafeRotate(),
                # A.ShiftScaleRotate(scale_limit=[-0.25,0.25], rotate_limit=90),
                # A.Perspective(),
                # NormalizeZScore(p=1),
                ToTensorV2()
            ], keypoint_params=A.KeypointParams(format='xy')
        )
    elif data_augmentation == "VAFFINE":
        transform = A.Compose(
            [
                A.SafeRotate(),
                A.Affine(scale=(0.9,1.1), translate_percent=(0,0.1), p=0.75),
                # A.Flip(),
                # A.ShiftScaleRotate(scale_limit=[-0.25,0.25], rotate_limit=90),
                # A.Perspective(),
                # NormalizeZScore(),
                ToTensorV2()
            ], keypoint_params=A.KeypointParams(format='xy')
        )
    elif data_augmentation == "V2":
        transform = A.Compose(
            [
            
                A.Downscale(),
                A.Flip(),
                A.ShiftScaleRotate(scale_limit=[-0.25,0.25], rotate_limit=90),
                # A.Perspective(),
                # NormalizeZScore(),
                ToTensorV2()
            ], keypoint_params=A.KeypointParams(format='xy')
        )
    elif data_augmentation == "V3":
        transform = A.Compose(
            [
                
                # A.GaussNoise(var_limit=15.0),
                A.Downscale(),
                A.Flip(),
                # A.Rotate(),
                A.ShiftScaleRotate(scale_limit=[-0.25,0.25], rotate_limit=90),

                A.Perspective(fit_output=True),
                # NormalizeZScore(),
                ToTensorV2()
            ], keypoint_params=A.KeypointParams(format='xy')
        )
    
    elif data_augmentation == "V4":
        transform = A.Compose(
            [
                
                # A.RandomBrightnessContrast(),
                # A.RandomGamma(gamma_limit=(80,100)),
                A.GaussNoise(var_limit=0.5),
                # A.CoarseDropout(),
                A.Downscale(),
                A.Flip(),
                A.ShiftScaleRotate(scale_limit=[-0.25,0.25], rotate_limit=90),
                A.Perspective(fit_output=True),
                # NormalizeZScore(),
                ToTensorV2()
            ], keypoint_params=A.KeypointParams(format='xy')
        )
    elif data_augmentation == "V5":
        transform = A.Compose(
            [
                A.Emboss(),
                # A.RandomGamma(gamma_limit=(80,100)),
                A.GaussNoise(var_limit=0.5),
                # A.CoarseDropout(),
                # A.RandomResizedCrop(input_size[0], input_size[1], p=0.25),
                A.ShiftScaleRotate(),
                A.Downscale(),
                A.Flip(),
                # A.SafeRotate(),
                A.Perspective(fit_output=True),
                # NormalizeZScore(),
                ToTensorV2()
            ], keypoint_params=A.KeypointParams(format='xy')
        )
    else:
        raise ValueError("transformations mode for dataaugmentation not recognised, try None, V1, V2, V3 or V4")
    
    return transform