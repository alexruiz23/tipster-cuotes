import pytest
from pydantic import ValidationError

from tests.factories import NOW, make_opportunity
from tipster.domain.models import Pick
from tipster.pricing.classify import Label


@pytest.mark.parametrize("label", [Label.VALUE, Label.POSIBLE_ERROR])
def test_value_y_posible_error_son_picks(label: Label) -> None:
    pick = Pick(quote_id=1, opportunity=make_opportunity(label), created_at=NOW)
    assert pick.opportunity.label is label


@pytest.mark.parametrize("label", [Label.SIN_VALOR, Label.DESCARTADA, Label.REVISION_MANUAL])
def test_el_resto_de_etiquetas_no_son_picks(label: Label) -> None:
    with pytest.raises(ValidationError):
        Pick(quote_id=1, opportunity=make_opportunity(label), created_at=NOW)
