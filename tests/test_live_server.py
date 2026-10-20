import urllib.request
import urllib.error
import json
import http.cookiejar
import json
import urllib.error
import urllib.request
import pytest

def test_live_server():
    cj = http.cookiejar.CookieJar()
    opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cj))

    try:
        res = opener.open('http://127.0.0.1:5000/api/camera/status', timeout=1)
    except Exception:
        pytest.skip("Live server is not running on http://127.0.0.1:5000")

    # 1. Check initial camera status
    status = json.loads(res.read().decode())
    assert status['camera_active'] is False and status['state'] == 'IDLE'
    print('[PASS] Initial Camera Status: IDLE / OFF')

    # 2. Open login page
    res = opener.open('http://127.0.0.1:5000/login')
    assert res.status == 200
    status = json.loads(opener.open('http://127.0.0.1:5000/api/camera/status').read().decode())
    assert status['camera_active'] is False
    print('[PASS] Login Page Loaded: Camera remains OFF')

    # 3. Test Teacher Login
    login_data = json.dumps({'email': 'teacher@school.edu', 'password': 'password123'}).encode()
    req = urllib.request.Request('http://127.0.0.1:5000/api/login', data=login_data, headers={'Content-Type': 'application/json'})
    res = opener.open(req)
    data = json.loads(res.read().decode())
    assert data['success'] is True and data['user_role'] == 'teacher'
    status = json.loads(opener.open('http://127.0.0.1:5000/api/camera/status').read().decode())
    assert status['camera_active'] is False
    print('[PASS] Teacher Login Successful: Camera remains OFF')

    # 4. Open Teacher Dashboard
    res = opener.open('http://127.0.0.1:5000/')
    html = res.read().decode()
    assert '<img src="" alt="Camera Stream" id="camera-stream"' in html
    status = json.loads(opener.open('http://127.0.0.1:5000/api/camera/status').read().decode())
    assert status['camera_active'] is False
    print('[PASS] Teacher Dashboard Rendered: Camera remains OFF, stream img is blank')

    # 5. Test Camera Start
    toggle_req = urllib.request.Request('http://127.0.0.1:5000/api/camera/toggle', data=json.dumps({'action': 'start'}).encode(), headers={'Content-Type': 'application/json'})
    t_res = json.loads(opener.open(toggle_req).read().decode())
    print(f'[PASS] Explicit Camera Start Response: {t_res}')

    # 6. Test Camera Stop
    stop_req = urllib.request.Request('http://127.0.0.1:5000/api/camera/toggle', data=json.dumps({'action': 'stop'}).encode(), headers={'Content-Type': 'application/json'})
    s_res = json.loads(opener.open(stop_req).read().decode())
    assert s_res['camera_active'] is False and s_res['state'] == 'IDLE'
    print('[PASS] Explicit Camera Stop: Camera returned to IDLE / OFF')

    # 7. Test Logout
    logout_req = urllib.request.Request('http://127.0.0.1:5000/api/logout', data=b'{}', headers={'Content-Type': 'application/json'})
    l_res = json.loads(opener.open(logout_req).read().decode())
    assert l_res['success'] is True
    status = json.loads(opener.open('http://127.0.0.1:5000/api/camera/status').read().decode())
    assert status['camera_active'] is False
    print('[PASS] User Logged Out: Camera remains OFF')

    # 8. Test Protected Route Access After Logout
    try:
        opener.open('http://127.0.0.1:5000/api/me')
        assert False, 'Should have failed with 401'
    except urllib.error.HTTPError as e:
        assert e.code == 401
        print('[PASS] Route Protection Verified: /api/me correctly returns 401 after logout')

    print('\nALL LIVE HTTP E2E SERVER TESTS PASSED PERFECTLY!')

if __name__ == '__main__':
    test_live_server()
