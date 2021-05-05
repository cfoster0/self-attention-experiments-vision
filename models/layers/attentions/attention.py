from functools import partial
from typing import Callable, Optional

from flax import linen as nn
from flax.linen import initializers
from jax import numpy as jnp
from jax.lax import Precision


class AttentionBlock(nn.Module):
    num_heads: int
    head_ch: Optional[int] = None
    out_ch: Optional[int] = None
    talking_heads: bool = False
    attn_drop_rate: float = 0.
    out_drop_rate: float = 0.
    use_bias: bool = False
    dtype: jnp.dtype = jnp.float32
    precision: Precision = Precision.DEFAULT
    kernel_init: Callable = initializers.kaiming_uniform()
    bias_init: Callable = initializers.zeros

    @nn.compact
    def __call__(self, inputs_q, inputs_kv, is_training: bool):
        assert inputs_q.ndim == inputs_kv.ndim == 3

        in_ch = inputs_q.shape[-1]
        assert in_ch % self.num_heads == 0
        head_ch = self.head_ch or int(in_ch / self.num_heads)
        out_ch = self.out_ch or in_ch

        dense = partial(nn.DenseGeneral,
                        axis=-1,
                        features=(self.num_heads, head_ch),
                        use_bias=self.use_bias,
                        dtype=self.dtype,
                        precision=self.precision,
                        kernel_init=self.kernel_init,
                        bias_init=self.bias_init)

        query = dense(name='queries')(inputs_q)
        key = dense(name='keys')(inputs_kv)
        value = dense(name='values')(inputs_kv)

        query = query / jnp.sqrt(head_ch)

        attn_weights = jnp.einsum('... q h d, ... k h d -> ... h q k',
                                  query,
                                  key,
                                  precision=self.precision)
        if self.talking_heads:
            pre_softmax_transform = self.param('pre_softmax', self.kernel_init,
                                               (self.num_heads, self.num_heads))
            attn_weights = jnp.einsum('... h q k, h i -> ... i q k',
                                      attn_weights,
                                      pre_softmax_transform,
                                      precision=self.precision)

        attn_weights = nn.softmax(attn_weights)

        if self.talking_heads:
            post_softmax_transform = self.param(
                'post_softmax', self.kernel_init,
                (self.num_heads, self.num_heads))
            attn_weights = jnp.einsum('... i q k, i h -> ... h q k',
                                      attn_weights,
                                      post_softmax_transform,
                                      precision=self.precision)

        attn_weights = nn.Dropout(rate=self.attn_dropout_rate)(
            attn_weights, deterministic=not is_training)

        attn_scores = jnp.einsum('... h q k, ... k h d -> ... q h d',
                                 attn_weights,
                                 value,
                                 precision=self.precision)

        output = nn.DenseGeneral(features=out_ch,
                                 axis=(-2, -1),
                                 use_bias=self.use_bias,
                                 dtype=self.dtype,
                                 precision=self.precision,
                                 kernel_init=self.kernel_init,
                                 bias_init=self.bias_init)(attn_scores)

        output = nn.Dropout(rate=self.out_drop_rate)(
            output, deterministic=not is_training)

        return output


class SelfAttentionBlock(nn.Module):
    num_heads: int
    head_ch: Optional[int] = None
    out_ch: Optional[int] = None
    talking_heads: bool = False
    attn_drop_rate: float = 0.
    out_drop_rate: float = 0.
    use_bias: bool = False
    dtype: jnp.dtype = jnp.float32
    precision: Precision = Precision.DEFAULT
    kernel_init: Callable = initializers.kaiming_uniform()
    bias_init: Callable = initializers.zeros

    @nn.compact
    def __call__(self, inputs, is_training: bool):
        return AttentionBlock(num_heads=self.num_heads,
                              head_ch=self.head_ch,
                              out_ch=self.out_ch,
                              talking_heads=self.talking_heads,
                              attn_drop_rate=self.attn_drop_rate,
                              out_drop_rate=self.out_drop_rate,
                              use_bias=self.use_bias,
                              dtype=self.dtype,
                              precision=self.precision,
                              kernel_init=self.kernel_init,
                              bias_init=self.bias_init)(inputs,
                                                        inputs,
                                                        is_training=is_training)
