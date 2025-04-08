"""
Service for transforming values between raw signal values and user-friendly formats.
"""
import logging
from typing import Any, Dict, Optional, Union

logger = logging.getLogger(__name__)

class TransformationService:
    """
    Handles transformations between raw signal values and display values.
    """
    
    def apply_transformation(
        self, value: Any, transform_config: Dict[str, Any]
    ) -> Any:
        """
        Apply a transformation to a value based on configuration.
        
        Args:
            value: The raw value to transform
            transform_config: Transformation configuration
            
        Returns:
            The transformed value
        """
        transform_type = transform_config.get('type')
        
        if transform_type == 'scale':
            return self._apply_scaling(value, transform_config)
        elif transform_type == 'map':
            return self._apply_mapping(value, transform_config)
        elif transform_type == 'boolean':
            return self._apply_boolean(value, transform_config)
        else:
            logger.warning(f"Unknown transformation type: {transform_type}")
            return value
    
    def apply_inverse_transformation(
        self, value: Any, transform_config: Dict[str, Any]
    ) -> Any:
        """
        Apply inverse transformation (from display value to raw value).
        
        Args:
            value: The display value to transform back to raw
            transform_config: Transformation configuration
            
        Returns:
            The raw value
        """
        transform_type = transform_config.get('type')
        
        if transform_type == 'scale':
            return self._apply_inverse_scaling(value, transform_config)
        elif transform_type == 'map':
            return self._apply_inverse_mapping(value, transform_config)
        elif transform_type == 'boolean':
            return self._apply_inverse_boolean(value, transform_config)
        else:
            logger.warning(f"Unknown inverse transformation type: {transform_type}")
            return value
            
    def _apply_scaling(
        self, value: Any, config: Dict[str, Any]
    ) -> Union[float, int]:
        """Apply scaling transformation: value * factor + offset."""
        try:
            factor = config.get('factor', 1.0)
            offset = config.get('offset', 0.0)
            precision = config.get('precision', None)
            
            # Convert value to float for calculation
            numeric_value = float(value)
            result = numeric_value * factor + offset
            
            # Apply precision if specified
            if precision is not None:
                result = round(result, precision)
                
            # Convert back to int if the result is a whole number and original was int
            if isinstance(value, int) and result.is_integer():
                return int(result)
                
            return result
        except (ValueError, TypeError) as e:
            logger.warning(f"Error applying scaling: {e}")
            return value
            
    def _apply_inverse_scaling(
        self, value: Any, config: Dict[str, Any]
    ) -> Union[float, int]:
        """Apply inverse scaling: (value - offset) / factor."""
        try:
            factor = config.get('factor', 1.0)
            offset = config.get('offset', 0.0)
            
            if factor == 0:
                logger.error("Cannot apply inverse scaling with factor=0")
                return value
                
            # Convert value to float for calculation
            numeric_value = float(value)
            result = (numeric_value - offset) / factor
            
            # Convert back to int if the result is a whole number
            if result.is_integer():
                return int(result)
                
            return result
        except (ValueError, TypeError) as e:
            logger.warning(f"Error applying inverse scaling: {e}")
            return value
            
    def _apply_mapping(self, value: Any, config: Dict[str, Any]) -> Any:
        """Apply mapping transformation using a dictionary lookup."""
        mapping = config.get('mapping', {})
        str_value = str(value)
        
        if str_value in mapping:
            return mapping[str_value]
        else:
            # Return default value if specified, otherwise original
            return config.get('default', value)
            
    def _apply_inverse_mapping(self, value: Any, config: Dict[str, Any]) -> Any:
        """Apply inverse mapping to convert display value back to raw value."""
        mapping = config.get('mapping', {})
        str_value = str(value)
        
        # Create inverse mapping
        inverse_mapping = {str(v): k for k, v in mapping.items()}
        
        if str_value in inverse_mapping:
            return inverse_mapping[str_value]
        else:
            # If no inverse mapping found, return original
            return value
            
    def _apply_boolean(self, value: Any, config: Dict[str, Any]) -> bool:
        """Convert value to boolean based on configuration."""
        true_values = config.get('true_values', [1, '1', 'true', 'True', True])
        return value in true_values
        
    def _apply_inverse_boolean(self, value: Any, config: Dict[str, Any]) -> Any:
        """Convert boolean back to raw value format."""
        true_raw = config.get('true_raw', 1)
        false_raw = config.get('false_raw', 0)
        
        # Convert to boolean and then to raw format
        bool_value = self._apply_boolean(value, config)
        return true_raw if bool_value else false_raw
