import jax.numpy as jnp
import jax
from .frequency_operation import FrequencyOperation

class Potential(FrequencyOperation):

    def __init__(self, n_grid : int):
        super().__init__(n_grid=n_grid)

    def __call__(
            self, 
            field : jax.Array, 
            G : float = 6.6743 * 10**(-11)):
        
        print(f"field shape{field.shape}")

        potential = jnp.fft.rfftn(
            field,  
            s=(self.n_grid, self.n_grid, self.n_grid), 
            axes=(1, 2, 3))
        
        potential = -4 * jnp.pi * potential * G * self.k

        potential = jnp.fft.irfftn(
            field,  
            s=(self.n_grid, self.n_grid, self.n_grid), 
            axes=(1, 2, 3))
        
        return potential