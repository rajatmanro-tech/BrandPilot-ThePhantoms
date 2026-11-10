from app.services import preflight
from app.services.visual_review import BrandKit, review_image
from PIL import Image


def test_preflight_flags_configured_rule_only():
    base = preflight.default_rules()["T-031"]
    kit = preflight.BrandKit(
        name="Test brand",
        rules={
            "T-031": preflight.Rule(
                "T-031", base.domain, "HIGH", "Banned superlative",
                "Brand rules", "test-rule", "Do not use unqualified superlatives."
            )
        },
        approved_claims={},
        outdated_since_years=(),
    )
    report = preflight.run_preflight(
        "Our best-in-class product is here.",
        kit=kit,
        reviewers={"terminology": preflight.terminology_reviewer},
    )
    assert report.complete
    assert any(item.rule_id == "T-031" for item in report.findings)


def test_visual_review_uses_supplied_palette():
    image = Image.new("RGB", (100, 100), (255, 255, 255))
    kit = BrandKit(
        palette={"paper": "#FFFFFF", "ink": "#000000"},
        wordmark_colors=["#000000"],
        text_ink="#000000",
    )
    result = review_image(image, kit, alt_text="A white square")
    assert "palette" in result["checks_run"]
    assert "degraded_checks" in result
