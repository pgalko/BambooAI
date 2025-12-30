import unittest
from tic_tac_toe import check_win, check_draw

class TestTicTacToe(unittest.TestCase):
    def test_row_win(self):
        board = ["X", "X", "X",
                 " ", " ", " ",
                 " ", " ", " "]
        self.assertTrue(check_win(board, "X"))

    def test_col_win(self):
        board = ["O", " ", " ",
                 "O", " ", " ",
                 "O", " ", " "]
        self.assertTrue(check_win(board, "O"))

    def test_diag_win(self):
        board = ["X", " ", " ",
                 " ", "X", " ",
                 " ", " ", "X"]
        self.assertTrue(check_win(board, "X"))

    def test_draw(self):
        board = ["X", "O", "X",
                 "O", "X", "O",
                 "O", "X", "O"]
        self.assertTrue(check_draw(board))
        self.assertFalse(check_win(board, "X"))
        self.assertFalse(check_win(board, "O"))

    def test_not_win(self):
        board = ["X", "O", "X",
                 " ", " ", " ",
                 " ", " ", " "]
        self.assertFalse(check_win(board, "X"))

if __name__ == '__main__':
    unittest.main()
