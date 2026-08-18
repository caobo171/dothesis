from urllib.parse import unquote

from app.http_headers import content_disposition


def test_unicode_attachment_header_is_ascii_and_preserves_utf8_filename():
    value = content_disposition("BẢNG HỎI.docx", "attachment")
    assert value.isascii()
    assert 'filename="BANG HOI.docx"' in value
    encoded = value.split("filename*=UTF-8''", 1)[1]
    assert unquote(encoded) == "BẢNG HỎI.docx"


def test_header_removes_newline_injection():
    value = content_disposition('report.docx\r\nX-Bad: yes', "attachment")
    assert "\r" not in value and "\n" not in value
