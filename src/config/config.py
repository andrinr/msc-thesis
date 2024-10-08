from typing import NamedTuple

class Config(NamedTuple):
    # Dataset
    grid_dir : str
    input_grid_size : int
    grid_size : int
    file_index_stride : int | list[int]
    file_index_steps : int
    file_index_start : int
    total_index_steps : int
    normalizing_function : str
    flip : bool

    # Training
    include_potential : bool
    sequential_skip_channels : int
    stepwise_epochs : int
    mixed_epochs : int
    sequential_epochs : int
    unique_networks : bool
    learning_rate : float
    model_dir : str
    model_type : str
    activation : str

    # FNO parameters
    fno_modes : int
    fno_input_channels : int
    fno_hidden_channels : int
    fno_output_channels : int
    fno_n_layers : int
    fno_increasing_modes : bool

    # UNet parameters
    unet_input_channels : int
    unet_hidden_channels : int
    unet_output_channels : int
    unet_num_levels : int

    # Cosmos
    box_size : int 
    num_particles : int
    omega_L : float
    omega_M : float
