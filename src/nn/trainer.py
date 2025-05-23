import jax.numpy as jnp
import jax
import optax
import equinox as eqx
from functools import partial
import time
from cosmos import PowerSpectrum
from typing import Tuple
from .metric import Metric
import time

# @partial(jax.jit)
# def mse(prediction : jax.Array, truth : jax.Array):
#     return jnp.mean((jax.nn.sigmoid(prediction) - jax.nn.sigmoid(truth))**2)

@partial(jax.jit)
def mse(prediction : jax.Array, truth : jax.Array):
    return jnp.mean((prediction - truth) ** 2)

@partial(jax.jit)
def mass_conservation_loss(prediction : jax.Array, truth : jax.Array):
    # [Batch, Frames, Channels, Depth, Height, Width]
    pred_mass = jnp.sum(prediction, axis=[3, 4, 5])
    true_mass = jnp.sum(truth, axis=[3, 4, 5])
    return jnp.mean((pred_mass - true_mass)**2)

@partial(jax.jit)
def power_spectrum_loss(prediction : jax.Array, truth : jax.Array):
    power_spectrum = PowerSpectrum(
        64, 20)
    p_pred, k = power_spectrum(prediction)
    p_true, k = power_spectrum(truth)

    return mse(jnp.log(p_pred), jnp.log(p_true))

@partial(jax.jit, static_argnums=[3])
def total_loss(
    prediction : jax.Array, 
    truth : jax.Array,
    attributes : jax.Array,
    single_state_loss : bool):
    
    #pl = 0.001 * power_loss(prediction, truth, attributes)

    if single_state_loss:
        mse_loss = mse(truth[:, -1], prediction[:, -1])
    else:
        mse_loss = mse(truth, prediction)

    return  mse_loss# + pl

@partial(jax.jit, static_argnums=[1, 4, 5, 6])
def prediction_loss(
        model_params : list,
        model_static : eqx.Module,
        sequence : jax.Array,
        attributes : jax.Array,
        sequential_mode : bool,
        add_potential : bool,
        single_state_loss : bool):
    
    """
    Prediction and MSE error. 

    shape of sequence:
    [Batch, Frames, Channels, Depth, Height, Width]
    """
    model = eqx.combine(model_params, model_static)
    model_fn = lambda x, y : model(x, y, sequential_mode, add_potential)
    pred = jax.vmap(model_fn)(sequence, attributes)

    loss = total_loss(pred, sequence[:, 1:], attributes[:, 1:], single_state_loss)

    return loss, pred

@partial(jax.jit, static_argnums=[3, 4, 5, 6])
def get_batch_loss(
        sequence : jax.Array,
        attributes : jax.Array,
        model_params,
        model_static : eqx.Module,
        sequential_mode : bool,
        add_potential : bool,
        single_state_loss : bool):
    
    # [Batch, Frames, Channels, Depth, Height, Width]

    # N = sequence.shape[3]
    
    loss, pred = prediction_loss(
        model_params,
        model_static,
        sequence,
        attributes,
        sequential_mode,
        add_potential,
        single_state_loss)
    
    # cross_correlation = jax.vmap(jax.vmap(jax.scipy.signal.correlate))(sequence[:, 1:], pred)
    mean_sequence = jnp.mean(sequence[:, 1:], axis=[2, 3, 4, 5], keepdims=True)

    mse = jnp.mean((pred - sequence[:, 1:])**2, axis=[2, 3, 4, 5])
    mse_default = jnp.mean((sequence[:, 1:]-mean_sequence)**2, axis=[2, 3, 4, 5])
    rse = jnp.mean(mse / mse_default)

    ae = jnp.mean(jnp.abs((pred - sequence[:, 1:])), axis=[2, 3, 4, 5])
    mae_default = jnp.mean(jnp.abs(sequence[:, 1:]-mean_sequence), axis=[2, 3, 4, 5])
    rae = jnp.mean(ae / mae_default)

    # # denormalize densities
    # get_power_fn = lambda x, y : jax.scipy.signal.correlate(in1=x, in2=y, mode="same", method="fft")

    # denormalize_map = jax.vmap(jax.vmap(normalize_inv))
    # power_map = jax.vmap(jax.vmap(get_power_fn))
    # overdensity_map = jax.vmap(jax.vmap(compute_overdensity))

    # # shift truth one frame ahead
    # rho_truth = denormalize_map(sequence[:, 1:, 0], attributes[:, 1:, 0], attributes[:, 1:, 1])
    # rho_pred = denormalize_map(pred[:, :, 0], attributes[:, 1:, 0], attributes[:, 1:, 1])

    # delta_truth = overdensity_map(rho_truth)
    # delta_pred = overdensity_map(rho_pred)

    # remove channel dim
    # c = power_map(delta_pred, delta_truth)
    # c = jnp.mean((delta_truth - delta_pred)**2)

    return loss, rae, rse

value_and_grad = eqx.filter_value_and_grad(prediction_loss, has_aux=True)

@partial(jax.jit, static_argnums=[3, 5, 6, 7, 8])
def learn_batch(
        sequence : jax.Array,
        attributes : jax.Array,
        model_params,
        model_static : eqx.Module,
        optimizer_state : optax.OptState,
        optimizer_static,
        sequential_mode : bool,
        add_potential : bool,
        single_state_loss : bool):
    """
    Learn model on batch of sequences.

    shape of sequence:
    [Batch, Frames, Channels, Depth, Height, Width]
    """

    (loss, _), grad = value_and_grad(
        model_params,
        model_static, 
        sequence,
        attributes,
        sequential_mode,
        add_potential,
        single_state_loss)
    
    updates, optimizer_state = optimizer_static.update(grad, optimizer_state)

    model = eqx.combine(model_params, model_static)
    model = eqx.apply_updates(model, updates)
    model_params, model_static = eqx.partition(model, eqx.is_array)

    return model_params, optimizer_state, loss

def train_model(
        model_params,
        model_static : eqx.Module,
        train_data_iterator,
        val_data_iterator,
        learning_rate : float,
        n_epochs : int,
        sequential_mode : bool,
        add_potential : bool,
        single_state_loss : bool) -> Tuple[eqx.Module, Metric]:
    
    start_total = time.time()
    
    optimizer = optax.adam(learning_rate)
    optimizer_state = optimizer.init(model_params)
    
    metric = Metric()

    for epoch in range(n_epochs):
        start = time.time()
        epoch_train_loss = []
        epoch_val_loss = []
        epoch_rae = []
        epoch_rse = []

        for _, data in enumerate(train_data_iterator):
            data_d = jax.device_put(data['data'], jax.devices('gpu')[0])
            attributes_d = jax.device_put(data['attributes'], jax.devices('gpu')[0])
            model_params, optimizer_state, loss = learn_batch(
                sequence = data_d,
                attributes = attributes_d,
                model_params = model_params,
                model_static = model_static,
                optimizer_state = optimizer_state,   
                optimizer_static = optimizer,
                sequential_mode = sequential_mode,
                add_potential = add_potential,
                single_state_loss = single_state_loss)
            epoch_train_loss.append(loss)

        for _, data in enumerate(val_data_iterator):
            data_d = jax.device_put(data['data'], jax.devices('gpu')[0])
            attributes_d = jax.device_put(data['attributes'], jax.devices('gpu')[0])
            loss, rae, rse = get_batch_loss(
                sequence = data_d,
                attributes = attributes_d,
                model_params = model_params,
                model_static= model_static,
                sequential_mode = sequential_mode,
                add_potential = add_potential,
                single_state_loss = single_state_loss)
            epoch_val_loss.append(loss)
            epoch_rae.append(rae)
            epoch_rse.append(rse)
        
        epoch_train_loss = jnp.array(epoch_train_loss)
        epoch_val_loss = jnp.array(epoch_val_loss)
        epoch_rae = jnp.array(epoch_rae)
        epoch_rse = jnp.array(epoch_rse)
        print(f"epoch {epoch}, train loss {epoch_train_loss.mean()}")
        print(f"epoch {epoch}, val loss {epoch_val_loss.mean()}")        
        print(f"epoch {epoch}, rae {epoch_rae.mean()}")
        print(f"epoch {epoch}, rse {epoch_rse.mean()}")
        print(f"epoch {epoch}, time {time.time() - start}")
        
        metric.update(
            epoch_train_loss.mean(),
            epoch_val_loss.mean(),
            epoch_rse.mean(),
            epoch_rae.mean(),
            time.time() - start_total)
        
    print(f"Training process done after {time.time() - start_total} s")
        
    return model_params, metric