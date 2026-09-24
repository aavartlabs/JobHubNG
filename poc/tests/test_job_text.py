from markupsafe import Markup

from jobhub_poc.webapp.job_text import format_description


def test_escaped_entities_read_as_text_not_codes():
    html = format_description("DataHub is an AI &amp; Data platform &mdash; 3,000+ users")
    assert "AI &amp; Data" in html  # one level of escaping: the browser shows "AI & Data"
    assert "&amp;amp;" not in html and "&amp;mdash;" not in html and "—" in html


def test_paragraphs_bullets_headings_and_bold():
    text = (
        "## About the role\n\nYou will run **production** systems.\n\n"
        "Requirements:\n- 5+ years\n* Kubernetes\n• Terraform\n\nClosing line."
    )
    html = str(format_description(text))
    assert "<h3>About the role</h3>" in html
    assert "<p>You will run <strong>production</strong> systems.</p>" in html
    assert "<h3>Requirements</h3>" in html
    assert "<ul><li>5+ years</li><li>Kubernetes</li><li>Terraform</li></ul>" in html
    assert "<p>Closing line.</p>" in html


def test_markdown_headings_lose_a_trailing_colon():
    assert "<h3>Minimum requirements</h3>" in str(format_description("### Minimum requirements:"))


def test_single_newlines_inside_a_paragraph_are_kept():
    assert "<p>line one<br>line two</p>" in str(format_description("line one\nline two"))


def test_no_html_from_the_source_ever_reaches_the_page():
    for evil in (
        "<script>alert(1)</script>hello",
        "&lt;script&gt;alert(1)&lt;/script&gt;hello",
        "<img src=x onerror=alert(1)>hello",
        "**<b onmouseover=alert(1)>x</b>**",
        "- <a href=\"javascript:alert(1)\">click</a>",
    ):
        html = str(format_description(evil))
        assert "<script" not in html and "onerror" not in html and "onmouseover" not in html
        assert "javascript:" not in html and "<a " not in html and "<img" not in html


def test_escaped_html_markup_becomes_plain_text_structure():
    html = str(format_description("&lt;p&gt;First&lt;/p&gt;&lt;ul&gt;&lt;li&gt;One&lt;/li&gt;&lt;/ul&gt;"))
    assert "First" in html and "One" in html and "&lt;" not in html


def test_empty_is_empty_markup():
    assert format_description(None) == Markup("")
    assert format_description("   ") == Markup("")
