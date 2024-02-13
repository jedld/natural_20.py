import unittest
from natural_20.py import blocks

class TestBlocks(unittest.TestCase):
    def test_active_selectors(self):
        # Create an instance of your class
        block = blocks.AutoLinearBlock(10, device="cpu")
        result = block.active_selectors()
        self.assertEqual(result, 11)

    def test_rediscretize(self):
        # Create an instance of your class
        block = blocks.AutoLinear(15, 10, device="cpu")
        # Generate a random tensor of shape (10) from the uniform distribution with range [0, 4)
        block.autoSelector.data = torch.randint(0, 6, (9,), dtype=torch.float32)
        test_input = torch.rand(15)
        with torch.no_grad():
            prev_result = block.forward(test_input)
            print(prev_result)
            print(block.selector_values())
            block.discretize()
            print(block.selector_values())
            new_result = block.forward(test_input)
            print(new_result)
            assert torch.allclose(prev_result, new_result, atol=1e-6), "Tensors are not close enough"