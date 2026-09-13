"""Name normalization utilities for GenesisLab assets.

This module provides utilities to normalize names (joints, bodies/links) from different
asset formats (URDF, MJCF, USD) to provide a consistent interface for configuration and matching.

The main issue is that USD format uses full path names like `/go2_description/joints/FL_hip_joint`,
while URDF/MJCF use short names like `FL_hip_joint`. This normalizer extracts the short
name from USD paths and provides a bidirectional mapping for both joints and bodies/links.
"""

from __future__ import annotations

import re
from typing import Dict, List, Optional, Tuple


class NameNormalizer:
    """Normalizes names (joints, bodies/links) from different asset formats to provide a consistent interface.
    
    This class handles the conversion between:
    - USD format: `/go2_description/joints/FL_hip_joint` -> `FL_hip_joint`
    - URDF/MJCF format: `FL_hip_joint` -> `FL_hip_joint` (no change)
    
    It provides bidirectional mapping and regex matching support for both joints and bodies/links.
    """

    def __init__(self, raw_names: List[str]):
        """Initialize the normalizer with raw names from the asset.
        
        Args:
            raw_names: List of names as they appear in the asset (may be USD paths).
        """
        self._raw_names = raw_names
        self._normalized_to_raw: Dict[str, str] = {}
        self._raw_to_normalized: Dict[str, str] = {}
        
        # Build bidirectional mapping
        for raw_name in raw_names:
            normalized = self._normalize_name(raw_name)
            # Handle potential collisions (multiple raw names mapping to same normalized name)
            if normalized not in self._normalized_to_raw:
                self._normalized_to_raw[normalized] = raw_name
            self._raw_to_normalized[raw_name] = normalized

    @staticmethod
    def _normalize_name(name: str) -> str:
        """Normalize a name by extracting the short name from USD paths.
        
        Args:
            name: Raw name (may be a USD path like `/go2_description/joints/FL_hip_joint`).
            
        Returns:
            Normalized short name (e.g., `FL_hip_joint`).
            
        Examples:
            >>> NameNormalizer._normalize_name("/go2_description/joints/FL_hip_joint")
            'FL_hip_joint'
            >>> NameNormalizer._normalize_name("FL_hip_joint")
            'FL_hip_joint'
            >>> NameNormalizer._normalize_name("/robot/base_joint")
            'base_joint'
            >>> NameNormalizer._normalize_name("/go2_description/links/base")
            'base'
        """
        # If it's a USD path (starts with /), extract the last component
        if name.startswith("/"):
            # Split by '/' and take the last non-empty component
            parts = [p for p in name.split("/") if p]
            if parts:
                return parts[-1]
        # For URDF/MJCF, return as-is
        return name

    @property
    def normalized_names(self) -> List[str]:
        """Get list of normalized names.
        
        Returns:
            List of normalized names (short names).
        """
        return list(self._normalized_to_raw.keys())

    @property
    def raw_names(self) -> List[str]:
        """Get list of raw names as they appear in the asset.
        
        Returns:
            List of raw names.
        """
        return self._raw_names

    def get_raw_name(self, normalized_name: str) -> Optional[str]:
        """Get the raw name from a normalized name.
        
        Args:
            normalized_name: Normalized name.
            
        Returns:
            Raw name, or None if not found.
        """
        return self._normalized_to_raw.get(normalized_name)

    def get_normalized_name(self, raw_name: str) -> Optional[str]:
        """Get the normalized name from a raw name.
        
        Args:
            raw_name: Raw name.
            
        Returns:
            Normalized name, or None if not found.
        """
        return self._raw_to_normalized.get(raw_name)

    def match_patterns(self, patterns: List[str]) -> Tuple[List[int], List[str]]:
        """Match regex patterns against normalized names.
        
        This method matches patterns against normalized names but returns indices
        and names in the order of the original raw names list.
        
        Args:
            patterns: List of regex patterns to match (e.g., ["FL_.*_joint", "FR_.*_joint"]).
            
        Returns:
            Tuple of (matched_indices, matched_normalized_names) where:
            - matched_indices: Indices in the original raw_names list
            - matched_normalized_names: Normalized names that matched (for reference)
            
        Raises:
            ValueError: If any pattern doesn't match any name.
        """
        matched_indices = []
        matched_normalized_names = []
        matched_set = set()
        
        normalized_names = self.normalized_names
        
        for pattern in patterns:
            pattern_matched = False
            regex = re.compile(f"^{pattern}$")
            
            for idx, raw_name in enumerate(self._raw_names):
                normalized = self._raw_to_normalized[raw_name]
                
                # Skip if already matched
                if idx in matched_set:
                    continue
                    
                # Match against normalized name
                if regex.match(normalized):
                    matched_indices.append(idx)
                    matched_normalized_names.append(normalized)
                    matched_set.add(idx)
                    pattern_matched = True
            
            if not pattern_matched:
                raise ValueError(
                    f"Pattern '{pattern}' did not match any names. "
                    f"Available normalized names: {normalized_names}"
                )
        
        return matched_indices, matched_normalized_names

    def normalize_pattern_dict(self, pattern_dict: Dict[str, any]) -> Dict[str, any]:
        """Normalize a pattern dictionary by ensuring patterns match normalized names.
        
        This is a helper method for configurations that use pattern dictionaries
        (e.g., default_joint_pos, stiffness, damping).
        
        Args:
            pattern_dict: Dictionary mapping regex patterns to values.
            
        Returns:
            The same dictionary (patterns should already work with normalized names).
        """
        # Patterns should already work with normalized names, so we just return as-is
        # This method exists for potential future normalization logic
        return pattern_dict
