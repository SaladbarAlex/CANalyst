from scripts.discover_rcd_models import NoRedirect, eligible_models


def test_only_online_supported_chat_models_are_candidates():
    def model(name, **kwargs):
        return dict(id=name, lifecycle=kwargs.get('lifecycle', 'active'),
                    instances_running=kwargs.get('online', 1),
                    endpoints=kwargs.get('endpoints', ['chat_completions']))
    assert eligible_models([
        model('active'), model('experimental', lifecycle='experimental'),
        model('retired', lifecycle='retired'), model('deprecated', lifecycle='deprecated'),
        model('offline', online=0), model('embedding', endpoints=['embedding']),
    ]) == ['active', 'experimental']


def test_catalog_redirect_is_not_followed_with_authorization():
    assert NoRedirect().redirect_request(None, None, 302, '', {}, 'https://example.com') is None
