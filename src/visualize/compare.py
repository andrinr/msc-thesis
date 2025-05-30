import jax
import jax.numpy as jnp
import matplotlib
import matplotlib.pyplot as plt
from config import Config
from mpl_toolkits.axes_grid1 import make_axes_locatable
from powerbox import get_power
from cosmos import compute_overdensity, to_redshift, normalize, normalize_inv, SpectralLoss
from matplotlib.cm import get_cmap

def compare(
        output_file: str,
        config: Config,
        sequences: list[jax.Array],
        predictions: list[jax.Array],
        labels : list[str],
        attributes: list[jax.Array],
        norm_functions : list[str]):

    # font = {'family' : 'normal',
    #     'weight' : 'regular',
    #     'size'   : 16}

    # matplotlib.rc('font', **font)

    num_predictions = len(predictions)  
    
    plt.rcParams.update({
        'font.size': 14,                   # Global font size
        'axes.labelsize': 16,              # X and Y label font size
        'axes.titlesize': 16,              # Title font size
        'xtick.labelsize': 12,             # X tick label font size
        'ytick.labelsize': 12,             # Y tick label font size
        'legend.fontsize': 14,             # Legend font size
        # 'axes.grid': True,                 # Enable grid
        'grid.alpha': 0.7,                 # Grid line transparency
        'grid.linestyle': '--',            # Grid line style
        'grid.color': 'gray',              # Grid line color
        'text.usetex': False,              # Use TeX for text (set True if TeX is available)
        'figure.figsize': [8, 6],          # Figure size
        'axes.prop_cycle': plt.cycler('color', ['#0077BB', '#EE7733', '#33BBEE', '#EE3377'])
    })

    print(num_predictions)

    N = sequences[0].shape[-1]

    # Create figure
    fig = plt.figure(layout='constrained', figsize=(4 + 3 * num_predictions, 10),  constrained_layout=True, dpi=300)
    subfigs = fig.subfigures(2, 1, wspace=0.07, hspace=0.1, height_ratios=[2, 1] if num_predictions > 0 else [1, 1])
    spec_sequence = subfigs[0].add_gridspec(2, num_predictions+1, wspace=0.3, hspace=0.1)
    spec_stats = subfigs[1].add_gridspec(1, 1)
    
    # Main sequence analysis part
    # ax_cdf = fig.add_subplot(spec_stats[0], adjustable='box', aspect=0.1)
    ax_power = fig.add_subplot(spec_stats[0], adjustable='box', aspect=0.1)
    # ax_phase = fig.add_subplot(spec_stats[1], adjustable='box', aspect=0.1)
    # ax_sl =  fig.add_subplot(spec_stats[1], adjustable='box', aspect=0.1)

    cmap = get_cmap('viridis')
    colors = cmap(jnp.linspace(0, 1, 6))
    
    file_index_stride = config.file_index_stride
    step = config.file_index_start

    frames = sequences[0].shape[0]
    grid_size = sequences[0].shape[2]
        
    sequence_curr = jnp.reshape(sequences[0], (frames, grid_size, grid_size, grid_size, 1))
    attributes_curr = attributes[0]
    attribs = jax.device_put(attributes_curr[1], device=jax.devices("gpu")[0])
    normalized = sequence_curr[-1]
    rho = normalize_inv(normalized, attribs, norm_functions[0])
    delta = compute_overdensity(rho)

    step = config.file_index_start

    ax_seq = fig.add_subplot(spec_sequence[1, 0])
    ax_seq.set_title(r'$\rho_{norm}$' + fr' $z={to_redshift(step/100):.2f}$')
    ax_seq.tick_params(left=False, bottom=False, labelleft=False, labelbottom=False)
    im_seq = ax_seq.imshow(normalized[grid_size // 2, :, :], cmap='inferno')
    divider = make_axes_locatable(ax_seq)
    cax = divider.append_axes('bottom', size='5%', pad=0.03)
    fig.colorbar(im_seq, cax=cax, orientation='horizontal')

    p, k = get_power(delta[:, :, :, 0], config.box_size)
    ax_power.plot(
        k,
        p,
        label=fr'sim $z = {to_redshift(step/100):.2f}$')
        # color=colors[frame])

    if isinstance(file_index_stride, list): 
        step = jnp.sum(jnp.array(file_index_stride)) + config.file_index_start
        file_index_stride.reverse()
    else:
        step = config.file_index_start + config.file_index_stride * (frames - 1)

    normalized = sequence_curr[0]
    ax_seq = fig.add_subplot(spec_sequence[0, 0])
    ax_seq.set_title(r'$\rho_{norm}$' + fr' $z={to_redshift(step/100):.2f}$')
    ax_seq.tick_params(left=False, bottom=False, labelleft=False, labelbottom=False)
    im_seq = ax_seq.imshow(normalized[grid_size // 2, :, :], cmap='inferno')
    divider = make_axes_locatable(ax_seq)
    cax = divider.append_axes('bottom', size='5%', pad=0.03)
    fig.colorbar(im_seq, cax=cax, orientation='horizontal')
    
    
    # Process predictions
    for idx in range(num_predictions):

        frames = sequences[idx].shape[0]
        grid_size = sequences[idx].shape[2]
        
        # Transform to shape for matplotlib
        sequence_curr = jnp.reshape(sequences[idx], (frames, grid_size, grid_size, grid_size, 1))
        pred_curr = jnp.reshape(predictions[idx], (frames - 1, grid_size, grid_size, grid_size, 1))
        attributes_curr = attributes[idx]
        
        frame = 0
        attribs = jax.device_put(attributes_curr[frame+1], device=jax.devices("gpu")[0])
        normalized = sequence_curr[frame+1]
        rho = normalize_inv(normalized, attribs, norm_functions[idx])
        delta = compute_overdensity(rho)

        rho_pred_normalized = pred_curr[frame]
        rho_pred = normalize_inv(rho_pred_normalized, attribs,  norm_functions[idx])
        delta_pred = compute_overdensity(rho_pred)

        normalized = sequence_curr[1]
        N = normalized.shape[1]
        # x shape : n_channels, N, N, N
        # x_fs shape : n_channels, N, N, N // 2, 2

        norm_fs = jnp.fft.rfftn(normalized, s=(N, N, N), axes=(0, 1, 2))
        kx = jnp.fft.fftfreq(N)[:, None, None]
        ky = jnp.fft.fftfreq(N)[None, :, None]
        kz = jnp.fft.rfftfreq(N)[None, None, :]

        k_squared = kx**2 + ky**2 + kz**2
        cutoff_k_squared = 0.02

        # Mask out higher wavelengths
        mask = (k_squared <= cutoff_k_squared)[:, :, :, None]
        # mask = k_squared <= cutoff_k_squared
        norm_fs_filtered = norm_fs * mask

        # Transform back to real space
        norm_filtered = jnp.fft.irfftn(norm_fs_filtered, s=(N, N, N), axes=(0, 1, 2))
        rho_pred_filtered = normalize_inv(norm_filtered, attribs,  norm_functions[idx])
        delta_pred_filtered = compute_overdensity(rho_pred_filtered)

        ax_seq = fig.add_subplot(spec_sequence[0, idx+1])
        ax_seq.set_title(r'$\hat{\rho}_{norm} - \rho_{norm}$')
        # ax_seq.set_title(r'filtered input $\rho_{norm}$')
        ax_seq.tick_params(left=False, bottom=False, labelleft=False, labelbottom=False)
        im_seq = ax_seq.imshow(
            rho_pred_normalized[grid_size // 2, :, :] - normalized[grid_size // 2, :, :], 
            cmap='RdYlBu',
            vmin=-0.15,
            vmax=0.15)
        # im_seq = ax_seq.imshow(norm_filtered[grid_size // 2, :, :], cmap='inferno')

        divider = make_axes_locatable(ax_seq)
        cax = divider.append_axes('bottom', size='5%', pad=0.03)
        fig.colorbar(
            im_seq, 
            cax=cax, 
            orientation='horizontal')
        
        # ax_cdf.hist(
        #     normalized.flatten(),
        #     20,
        #     density=True,
        #     log=True,
        #     histtype="step",
        #     cumulative=False,
        #     label=fr'sim $z = {to_redshift(step/100):.2f}$')
        #     # color=colors[frame])

        ax_seq_pred = fig.add_subplot(spec_sequence[1, idx+1])
        ax_seq_pred.tick_params(left=False, bottom=False, labelleft=False, labelbottom=False)
        ax_seq_pred.set_title(r'$\hat{\rho}_{norm}$' + f' {labels[idx]}')
        im_seq_pred = ax_seq_pred.imshow(rho_pred_normalized[grid_size // 2, :, :], cmap='inferno')
        
        divider_pred = make_axes_locatable(ax_seq_pred)
        cax_pred = divider_pred.append_axes('bottom', size='5%', pad=0.03)
        fig.colorbar(im_seq_pred, cax=cax_pred, orientation='horizontal')
        
        # ax_cdf.hist(
        #     rho_pred_normalized.flatten(),
        #     100,
        #     density=True,
        #     log=True,
        #     histtype="step",
        #     cumulative=False,
        #     label=fr'pred {labels[idx]} $z = {to_redshift(step/100):.2f}$')
        #     # color=colors[frame + 1])
        
        p_pred, k_pred = get_power(delta_pred[:, :, :, 0], config.box_size)
        ax_power.plot(
            k_pred, p_pred,
            label=fr'pred {labels[idx]}')
        
        # k_pred, p_pred = spectral_loss(delta_pred[:, :, :, 0], delta[:, :, :, 0])
        # ax_phase.plot(
        #     k_pred, p_pred,
        #     label=fr'pred {labels[idx]}')
        
        # k, p = spectral_loss(delta_pred[:, :, :, 0], delta[:, :, :, 0])
        # print(k)
        # print(p)
        # k *= 60
        # ax_sl.plot(
        #     k, p,  label=fr'pred {labels[idx]}')
        
        # p_pred, k_pred = get_power(delta_pred_filtered[:, :, :, 0], config.box_size)
        # ax_power.plot(
        #     k_pred, p_pred,
        #     label=fr'filtered z={labels[idx]}')
        #     # color=colors[frame + 1])

    # Finalize plots
    
    # ax_sl.set_yscale('log')
    # ax_sl.set_xscale('log')
    ax_power.set_yscale('log')
    ax_power.set_xscale('log')
    ax_power.legend(loc='center left', bbox_to_anchor=(1, 0.5))
    ax_power.set_title(r'Power Spectrum of $\delta$')
    ax_power.set_xlabel(r'$k$ [$h \ \mathrm{Mpc}^{-1}$]')
    ax_power.set_ylabel(r'$P(k)$ [$h^{-3} \ \mathrm{Mpc}^3$]')
    # ax_cdf.set_title(r'pdf $\rho_{norm}$')
    # ax_cdf.legend(loc='center left', bbox_to_anchor=(1, 0.5))

    plt.savefig(output_file, bbox_inches="tight", dpi=300)