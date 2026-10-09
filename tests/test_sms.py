import httpx
import pytest

from app.exceptions.handler import ServiceException
from app.utils import sms


class _Response:
    status_code = 201
    text = ""

    def json(self):
        return {"sid": "SM123"}


@pytest.fixture
def twilio(monkeypatch):
    monkeypatch.setattr(sms.settings, "TWILIO_ACCOUNT_SID", "AC123")
    monkeypatch.setattr(sms.settings, "TWILIO_AUTH_TOKEN", "secret")
    monkeypatch.setattr(sms.settings, "TWILIO_FROM_NUMBER", "+15550000000")
    monkeypatch.setattr(sms, "_CONNECT_RETRY_DELAY_SECONDS", 0)
    calls = []

    def answer_with(*outcomes):
        def post(*_args, **_kwargs):
            outcome = outcomes[len(calls)]
            calls.append(outcome)
            if isinstance(outcome, Exception):
                raise outcome
            return outcome

        monkeypatch.setattr(sms.httpx, "post", post)

    return answer_with, calls


def test_retries_once_when_it_could_not_reach_twilio(twilio):
    # e.g. "[Errno -3] Temporary failure in name resolution": nothing was sent yet.
    answer_with, calls = twilio
    answer_with(httpx.ConnectError("Temporary failure in name resolution"), _Response())

    sms.send_registration_sms("+5491100000000", "123456")

    assert len(calls) == 2


def test_gives_up_after_the_one_retry(twilio):
    answer_with, calls = twilio
    answer_with(httpx.ConnectError("dns"), httpx.ConnectError("dns"))

    with pytest.raises(ServiceException) as raised:
        sms.send_registration_sms("+5491100000000", "123456")

    assert raised.value.status_code == 502
    assert len(calls) == 2


def test_does_not_retry_a_timeout_that_may_already_have_sent_it(twilio):
    answer_with, calls = twilio
    answer_with(httpx.ReadTimeout("read timed out"))

    with pytest.raises(ServiceException):
        sms.send_registration_sms("+5491100000000", "123456")

    assert len(calls) == 1
