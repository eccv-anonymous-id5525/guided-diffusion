import argparse

from . import gaussian_diffusion as gd
from .respace import SpacedDiffusion, space_timesteps
from .models.unet_deca import UNetModelCondition, UNetModel
from .models.dense_deca import DenseDDPM, AutoEncoderDPM, DECADenseCond

NUM_CLASSES = 1000

# Pipeline
def create_img_deca_and_diffusion(cfg):
    img_model = create_model(cfg.img_model)
    params_model = create_param_model(cfg.param_model)
    diffusion = create_gaussian_diffusion(cfg.diffusion)
    return img_model, params_model, diffusion

def create_deca_and_diffusion(cfg):
    param_model = create_param_model(cfg.param_model)
    diffusion = create_gaussian_diffusion(cfg.diffusion)
    return param_model, diffusion

def create_img_and_diffusion(cfg):
    img_model = create_model(cfg.img_model)
    diffusion = create_gaussian_diffusion(cfg.diffusion)
    return img_model, diffusion

# Each sub-modules
def create_param_model(cfg):
    if cfg.deca_cond:
        return DECADenseCond(
            in_channels=cfg.in_channels,
            out_channels=cfg.out_channels,
            model_channels=cfg.model_channels,
            use_checkpoint=cfg.use_checkpoint,
            use_scale_shift_norm=cfg.use_scale_shift_norm
        )
    else:
        if cfg.arch == 'magenta':
            print('magenta')
            return DenseDDPM(
                in_channels=cfg.in_channels,
                model_channels=cfg.model_channels,
                num_layers=cfg.num_layers,
                use_checkpoint=cfg.use_checkpoint,
            )
        elif cfg.arch == 'autoenc':
            print('autoenc')
            return AutoEncoderDPM(
                in_channels=cfg.in_channels,
                out_channels=cfg.out_channels,
                model_channels=cfg.model_channels,
                num_layers=cfg.num_layers,
                use_checkpoint=cfg.use_checkpoint,
            )
        else: raise NotImplementedError

def create_model(cfg):
    if cfg.channel_mult == "":
        if cfg.image_size == 512:
            channel_mult = (0.5, 1, 1, 2, 2, 4, 4)
        elif cfg.image_size == 256:
            channel_mult = (1, 1, 2, 2, 4, 4)
        elif cfg.image_size == 128:
            channel_mult = (1, 1, 2, 3, 4)
        elif cfg.image_size == 64:
            channel_mult = (1, 2, 3, 4)
        else:
            raise ValueError(f"unsupported image size: {cfg.image_size}")
    else:
        channel_mult = tuple(int(ch_mult) for ch_mult in cfg.channel_mult.split(","))

    attention_ds = []
    for res in cfg.attention_resolutions.split(","):
        attention_ds.append(cfg.image_size // int(res))

    if cfg.arch == 'UNet':
        return UNetModel(
            image_size=cfg.image_size,
            in_channels=cfg.in_channels,
            model_channels=cfg.num_channels,
            out_channels=cfg.out_channels,
            num_res_blocks=cfg.num_res_blocks,
            attention_resolutions=tuple(attention_ds),
            dropout=cfg.dropout,
            channel_mult=channel_mult,
            num_classes=(NUM_CLASSES if cfg.class_cond else None),
            use_checkpoint=cfg.use_checkpoint,
            num_heads=cfg.num_heads,
            num_head_channels=cfg.num_head_channels,
            num_heads_upsample=cfg.num_heads_upsample,
            use_scale_shift_norm=cfg.use_scale_shift_norm,
            resblock_updown=cfg.resblock_updown,
            use_new_attention_order=cfg.use_new_attention_order,
            condition=False,
        )
    elif cfg.arch == 'UNetCond':
        return UNetModelCondition(
            image_size=cfg.image_size,
            in_channels=cfg.in_channels,
            model_channels=cfg.num_channels,
            out_channels=cfg.out_channels,
            num_res_blocks=cfg.num_res_blocks,
            attention_resolutions=tuple(attention_ds),
            dropout=cfg.dropout,
            channel_mult=channel_mult,
            num_classes=(NUM_CLASSES if cfg.class_cond else None),
            use_checkpoint=cfg.use_checkpoint,
            num_heads=cfg.num_heads,
            num_head_channels=cfg.num_head_channels,
            num_heads_upsample=cfg.num_heads_upsample,
            use_scale_shift_norm=cfg.use_scale_shift_norm,
            resblock_updown=cfg.resblock_updown,
            use_new_attention_order=cfg.use_new_attention_order,
            condition_dim=cfg.condition_dim,
            condition=True,
        )
    else: raise NotImplementedError

def create_gaussian_diffusion(cfg):
    betas = gd.get_named_beta_schedule(cfg.noise_schedule, cfg.diffusion_steps)
    if cfg.use_kl:
        loss_type = gd.LossType.RESCALED_KL
    elif cfg.rescale_learned_sigmas:
        loss_type = gd.LossType.RESCALED_MSE
    else:
        loss_type = gd.LossType.MSE
    if not cfg.timestep_respacing:
        timestep_respacing = [cfg.diffusion_steps]
    return SpacedDiffusion(
        use_timesteps=space_timesteps(cfg.diffusion_steps, timestep_respacing),
        betas=betas,
        model_mean_type=(
            gd.ModelMeanType.EPSILON if not cfg.predict_xstart else gd.ModelMeanType.START_X
        ),
        model_var_type=(
            (
                gd.ModelVarType.FIXED_LARGE
                if not cfg.sigma_small
                else gd.ModelVarType.FIXED_SMALL
            )
            if not cfg.learn_sigma
            else gd.ModelVarType.LEARNED_RANGE
        ),
        loss_type=loss_type,
        rescale_timesteps=cfg.rescale_timesteps,
    )

# Utils
def add_dict_to_argparser(parser, default_dict):
    for k, v in default_dict.items():
        v_type = type(v)
        if v is None:
            v_type = str
        elif isinstance(v, bool):
            v_type = str2bool
        parser.add_argument(f"--{k}", default=v, type=v_type)

def args_to_dict(args, keys):
    return {k: getattr(args, k) for k in keys}

def str2bool(v):
    """
    https://stackoverflow.com/questions/15008758/parsing-boolean-values-with-argparse
    """
    if isinstance(v, bool):
        return v
    if v.lower() in ("yes", "true", "t", "y", "1"):
        return True
    elif v.lower() in ("no", "false", "f", "n", "0"):
        return False
    else:
        raise argparse.ArgumentTypeError("boolean value expected")

def seed_all(seed: int):

    """
    Seeding everything for paired indendent training

    :param seed: seed number for a number generator.
    """

    import os
    import numpy as np
    import torch as th
    import random
    random.seed(seed)
    os.environ['PYTHONHASHSEED'] = str(seed)
    np.random.seed(seed)
    th.manual_seed(seed)
    th.cuda.manual_seed(seed)
    th.cuda.manual_seed_all(seed)
    th.backends.cudnn.deterministic = True
    th.backends.cudnn.benchmark = False