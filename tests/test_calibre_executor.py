from unittest.mock import patch, MagicMock
from core.function_executor import FunctionExecutor


def _make_executor():
    return FunctionExecutor()


def _book(title="Dune", author="Frank Herbert", year="1965",
          formats=None, description="Epic sci-fi.", bid=1):
    formats = formats or ["epub", "pdf"]
    return {
        "id": bid,
        "title": title,
        "author": author,
        "year": year,
        "formats": formats,
        "description": description,
        "download_url": f"http://localhost:8083/api/books/{bid}/download/epub",
    }


def test_search_book_success():
    ex = _make_executor()
    with patch("core.calibre_manager.calibre_manager") as cm:
        cm.search_books.return_value = [_book()]
        result = ex.execute("search_book", {"query": "Dune"})
    assert result["success"] is True
    assert "Dune" in result["message"]
    assert "Frank Herbert" in result["message"]
    assert "epub" in result["message"].lower()
    assert "localhost:8083" in result["message"]


def test_search_book_no_results():
    ex = _make_executor()
    with patch("core.calibre_manager.calibre_manager") as cm:
        cm.search_books.return_value = []
        result = ex.execute("search_book", {"query": "unknownxyz"})
    assert result["success"] is False
    assert "unknownxyz" in result["message"]


def test_search_book_no_url_configured():
    ex = _make_executor()
    with patch("core.calibre_manager.calibre_manager") as cm:
        cm.search_books.return_value = []
        result = ex.execute("search_book", {"query": "Dune"})
    assert result["success"] is False


def test_search_book_description_truncated():
    ex = _make_executor()
    long_desc = "A" * 500
    with patch("core.calibre_manager.calibre_manager") as cm:
        cm.search_books.return_value = [_book(description=long_desc)]
        result = ex.execute("search_book", {"query": "Dune"})
    assert result["success"] is True
    # description is truncated to ≤ 200 chars in the message
    assert long_desc not in result["message"]


def test_search_book_multiple_results():
    ex = _make_executor()
    books = [_book("Dune", bid=1), _book("Dune Messiah", bid=2)]
    with patch("core.calibre_manager.calibre_manager") as cm:
        cm.search_books.return_value = books
        result = ex.execute("search_book", {"query": "Dune"})
    assert result["success"] is True
    assert "Dune" in result["message"]
    assert "Dune Messiah" in result["message"]


def test_search_book_with_search_type():
    ex = _make_executor()
    with patch("core.calibre_manager.calibre_manager") as cm:
        cm.search_books.return_value = [_book()]
        result = ex.execute("search_book", {"query": "Herbert", "search_type": "author"})
    cm.search_books.assert_called_once_with("Herbert", "author", 3)
    assert result["success"] is True


def test_search_book_no_description():
    ex = _make_executor()
    with patch("core.calibre_manager.calibre_manager") as cm:
        cm.search_books.return_value = [_book(description="")]
        result = ex.execute("search_book", {"query": "Dune"})
    assert result["success"] is True
    assert "Dune" in result["message"]
