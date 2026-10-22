import pytest
from lumen import private_browser


def test_private_window_passes_url_as_one_literal_argument(monkeypatch):
    url='https://example.org/search?q=a&name=$(no-command)'
    monkeypatch.setattr(private_browser.sys,'platform','linux')
    monkeypatch.setattr(private_browser.shutil,'which',lambda name:'/bin/firefox' if name=='firefox' else None)
    calls=[]
    monkeypatch.setattr(private_browser.subprocess,'Popen',lambda command,**kwargs:calls.append((command,kwargs)))
    private_browser.open_private(url)
    assert calls[0][0]==['/bin/firefox','--private-window',url]
    assert not calls[0][1].get('shell')


def test_windows_uses_default_supported_browser_then_other_installed_browsers(monkeypatch,tmp_path):
    browser=tmp_path/'msedge.exe';browser.touch()
    unsupported=tmp_path/'other-browser.exe';unsupported.touch()
    monkeypatch.setattr(private_browser.sys,'platform','win32')
    monkeypatch.setattr(private_browser,'_windows_candidates',lambda:iter([str(unsupported),str(browser)]))
    assert list(private_browser.private_commands('https://example.org'))==[[str(browser),'--inprivate','https://example.org']]


def test_failure_does_not_silently_open_a_normal_window(monkeypatch):
    monkeypatch.setattr(private_browser,'private_commands',lambda url:iter([['not-present','--incognito',url]]))
    def fail(*args,**kwargs):raise FileNotFoundError()
    monkeypatch.setattr(private_browser.subprocess,'Popen',fail)
    with pytest.raises(RuntimeError,match='无痕浏览器'):private_browser.open_private('https://example.org')


@pytest.mark.parametrize('url',['file:///etc/passwd','javascript:alert(1)','magnet:?xt=abc','https://user:secret@example.org/','http:///missing'])
def test_only_website_addresses_go_to_browser(url):
    with pytest.raises(ValueError):list(private_browser.private_commands(url))
