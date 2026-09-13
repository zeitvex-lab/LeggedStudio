"""Wrapper for delay buffer to adapt IsaacLab-style interface.

This module provides a wrapper to adapt genesislab's DelayBuffer to IsaacLab's DelayBuffer interface.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import TYPE_CHECKING

import torch

from genesislab.components.additional.buffers import DelayBuffer

if TYPE_CHECKING:
    pass


class IsaacLabStyleDelayBuffer:
    """Wrapper to adapt genesislab's DelayBuffer to IsaacLab's DelayBuffer interface.

    This wrapper provides the IsaacLab-style interface (history_length, batch_size, device)
    and methods (set_time_lag, compute(data)) while using genesislab's DelayBuffer internally.
    """

    def __init__(self, history_length: int, batch_size: int, device: str):
        """Initialize the delay buffer wrapper.

        Args:
            history_length: Maximum delay in time steps.
            batch_size: Number of parallel environments.
            device: Device for tensor operations.
        """
        self._history_length = history_length
        self._batch_size = batch_size
        self._device = device

        # Use genesislab's DelayBuffer with min_lag=0, max_lag=history_length
        self._buffer = DelayBuffer(
            min_lag=0,
            max_lag=history_length,
            batch_size=batch_size,
            device=device,
            per_env=True,  # Each environment has its own lag
            hold_prob=0.0,  # No hold probability
            update_period=0,  # Update every step
            per_env_phase=False,  # No phase offset needed
        )

    def set_time_lag(self, time_lag: int | torch.Tensor, batch_ids: Sequence[int] = None):
        """Set the time lag for the delay buffer.

        Args:
            time_lag: The desired delay (int or tensor).
            batch_ids: Batch indices to set, or None for all.
        """
        if isinstance(time_lag, int):
            # If int, create a tensor with the same value for all batch indices
            if batch_ids is None:
                lags = torch.full((self._batch_size,), time_lag, dtype=torch.long, device=self._device)
            else:
                if isinstance(batch_ids, slice):
                    batch_ids = list(range(*batch_ids.indices(self._batch_size)))
                lags = torch.full((len(batch_ids),), time_lag, dtype=torch.long, device=self._device)
        else:
            # If tensor, use it directly
            lags = time_lag.to(device=self._device, dtype=torch.long)

        # Clamp to valid range
        lags = lags.clamp(0, self._history_length)
        self._buffer.set_lags(lags, batch_ids)

    def reset(self, batch_ids: Sequence[int] = None):
        """Reset the delay buffer.

        Args:
            batch_ids: Batch indices to reset, or None for all.
        """
        self._buffer.reset(batch_ids)

    def compute(self, data: torch.Tensor) -> torch.Tensor:
        """Append data and return delayed version.

        Args:
            data: Input data tensor of shape (batch_size, ...).

        Returns:
            Delayed data tensor of the same shape.
        """
        self._buffer.append(data)
        return self._buffer.compute()
