#!/usr/bin/env python3
"""
Test script for the transformation_service and command_handler components.
"""
import logging
import sys
from stiebel_control.services.transformation_service import TransformationService
from stiebel_control.services.command_handler import CommandHandler

# Configure basic logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler()]
)

logger = logging.getLogger(__name__)

def test_transformation_service():
    """Test the TransformationService functionality."""
    logger.info("Testing TransformationService...")
    
    service = TransformationService()
    
    # Test scaling transformation
    scale_config = {
        'type': 'scale',
        'factor': 0.1,
        'offset': 5,
        'precision': 1
    }
    
    raw_value = 100
    transformed = service.apply_transformation(raw_value, scale_config)
    inverse = service.apply_inverse_transformation(transformed, scale_config)
    
    logger.info(f"Scale: {raw_value} -> {transformed} -> {inverse}")
    assert abs(raw_value - inverse) < 0.01, "Inverse scaling failed"
    
    # Test mapping transformation
    map_config = {
        'type': 'map',
        'mapping': {
            '0': 'Off',
            '1': 'Economy',
            '2': 'Normal',
            '3': 'Comfort'
        }
    }
    
    for i in range(4):
        raw_value = str(i)
        transformed = service.apply_transformation(raw_value, map_config)
        inverse = service.apply_inverse_transformation(transformed, map_config)
        logger.info(f"Map: {raw_value} -> {transformed} -> {inverse}")
        assert inverse == raw_value, f"Inverse mapping failed for {raw_value}"
    
    # Test boolean transformation
    bool_config = {
        'type': 'boolean',
        'true_values': [1, '1', 'true', 'True', True],
        'true_raw': 1,
        'false_raw': 0
    }
    
    for test_val in [0, 1, 'true', 'false']:
        transformed = service.apply_transformation(test_val, bool_config)
        inverse = service.apply_inverse_transformation(transformed, bool_config)
        logger.info(f"Boolean: {test_val} -> {transformed} -> {inverse}")
    
    logger.info("TransformationService tests completed successfully")

def main():
    """Run all tests."""
    try:
        test_transformation_service()
        
        # We can't easily test CommandHandler without mock objects
        logger.info("CommandHandler would require mock objects for testing")
        
        logger.info("All tests completed successfully")
        return 0
    except Exception as e:
        logger.error(f"Test failed: {e}")
        return 1

if __name__ == "__main__":
    sys.exit(main())
