from disclaimrwebadmin.html_text import html_to_text


def test_paragraphs_and_br():
    assert html_to_text("<p>Hello</p><p>World<br>again</p>") == "Hello\nWorld\nagain"


def test_tinymce_spans_and_inline_formatting():
    html = (
        '<p><span style="font-size: 12pt; color: #345a8c;"><strong>{resolver["cn"]}</strong>'
        "</span><br><em>Sales</em> <u>Dept</u></p>\n"
        '<p><span style="font-family: arial;">{sender}</span></p>'
    )
    assert html_to_text(html) == '{resolver["cn"]}\nSales Dept\n{sender}'


def test_link_with_different_text():
    assert html_to_text('<a href="https://x.org/a">Site</a>') == "Site <https://x.org/a>"


def test_link_with_identical_text_and_no_href():
    assert html_to_text('<a href="https://x.org">https://x.org</a>') == "https://x.org"
    assert html_to_text("<a>just text</a>") == "just text"


def test_mailto_and_tel_links():
    assert html_to_text('<a href="mailto:a@b.de">a@b.de</a>') == "a@b.de"
    assert html_to_text('<a href="tel:+49123">+49123</a>') == "+49123"
    assert html_to_text('<a href="mailto:a@b.de">Mail me</a>') == "Mail me <mailto:a@b.de>"


def test_table_cells_and_image_placeholder():
    html = (
        '<table><tbody><tr><td>{image["logo"]}</td>'
        '<td><p>{resolver["cn"]}</p><p>{resolver["telephoneNumber"]}</p></td></tr></tbody></table>'
    )
    assert html_to_text(html) == '{resolver["cn"]}\n{resolver["telephoneNumber"]}'
    assert html_to_text("<table><tr><td>A</td><td>B</td></tr><tr><td>C</td><td>D</td></tr></table>") == (
        "A  B\nC  D"
    )


def test_hr():
    assert html_to_text("<p>Hi</p><hr><p>Bye</p>") == "Hi\n--\nBye"


def test_entities_and_nbsp():
    assert html_to_text("<p>Fish &amp; Chips&nbsp;&nbsp;Ltd &lt;x&gt;</p>") == "Fish & Chips Ltd <x>"


def test_placeholders_kept():
    html = '<p>{resolver["displayName"]} {header["subject"]}</p><p>{rt}x{/rt}</p>'
    assert html_to_text(html) == '{resolver["displayName"]} {header["subject"]}\n{rt}x{/rt}'


def test_image_placeholder_removed_with_its_line():
    html = '<p>Top</p><p>{image["a-b"]}</p><p>Bottom {image["x"]}</p>'
    assert html_to_text(html) == "Top\nBottom"
    assert html_to_text('<img src="x.png"><p>Text</p>') == "Text"


def test_blank_lines_collapsed_and_trimmed():
    html = "<p>&nbsp;</p><p>a</p><p>&nbsp;</p><p>&nbsp;</p><p>&nbsp;</p><p>b   \t c</p><p>&nbsp;</p>"
    assert html_to_text(html) == "a\n\nb c"


def test_empty_input():
    assert html_to_text("") == ""
    assert html_to_text("  \n ") == ""
    assert html_to_text("<p>&nbsp;</p>") == ""
