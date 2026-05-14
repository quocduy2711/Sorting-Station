"""
Tests for sorting logic.
"""
import pytest
from control.sorting_logic import SortingLogic

def test_valid_product_routing():
    logic = SortingLogic()
    assert logic.get_sorter_for_product(1) == 1
    assert logic.get_sorter_for_product(3) == 2
    assert logic.get_sorter_for_product(5) == 3

def test_invalid_product_routing():
    logic = SortingLogic()
    with pytest.raises(ValueError):
        logic.get_sorter_for_product(99)

def test_product_info():
    logic = SortingLogic()
    shape, color = logic.get_product_info(1)
    assert shape == "Flat"
    assert color == "Blue"
