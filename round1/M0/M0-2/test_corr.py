import os
import sys
import unittest

# 把上级目录加入 Python 搜索路径，这样才能 import 到 corr.py
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from corr import pearson


class TestPearson(unittest.TestCase):

    def test_perfect_positive(self):
        """[1,2,3] 与 [2,4,6] 应完全正相关，r = 1.0"""
        n, mean_x, mean_y, r = pearson([1, 2, 3], [2, 4, 6])
        self.assertAlmostEqual(r, 1.0, places=6)

    def test_perfect_negative(self):
        """[1,2,3] 与 [6,4,2] 应完全负相关，r = -1.0"""
        n, mean_x, mean_y, r = pearson([1, 2, 3], [6, 4, 2])
        self.assertAlmostEqual(r, -1.0, places=6)

    def test_empty_data(self):
        """空数据应抛出 ValueError"""
        with self.assertRaises(ValueError):
            pearson([], [])

    def test_length_mismatch(self):
        """两列长度不一致应抛出 ValueError"""
        with self.assertRaises(ValueError):
            pearson([1, 2, 3], [1, 2])

    def test_zero_variance(self):
        """某列方差为 0 应抛出 ValueError"""
        with self.assertRaises(ValueError):
            pearson([1, 1, 1], [1, 2, 3])


if __name__ == "__main__":
    unittest.main()