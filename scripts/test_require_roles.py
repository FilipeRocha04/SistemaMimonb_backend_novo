import sys, os
# Ensure project root (backend) is on sys.path so `app` package can be imported when this script is run directly
sys.path.append(os.path.dirname(os.path.dirname(__file__)))

from app.services.auth import require_roles
from app.models.user import RoleEnum
from fastapi import HTTPException


class DummyUser:
    def __init__(self, papel):
        self.papel = papel


def run_tests():
    print('Testing require_roles logic...')

    checker = require_roles('garcom', 'admin', 'pizzaiolo')

    # allowed enum (garcom)
    u1 = DummyUser(RoleEnum.garcom)
    try:
        out = checker(current_user=u1)
        assert out is u1
        print('PASS: enum role allowed')
    except HTTPException:
        print('FAIL: enum role should be allowed')

    # allowed string (admin)
    u2 = DummyUser('admin')
    try:
        out = checker(current_user=u2)
        assert out is u2
        print('PASS: string role allowed')
    except HTTPException:
        print('FAIL: string role should be allowed')

    # allowed enum (pizzaiolo)
    u4 = DummyUser(RoleEnum.pizzaiolo)
    try:
        out = checker(current_user=u4)
        assert out is u4
        print('PASS: pizzaiolo enum role allowed')
    except HTTPException:
        print('FAIL: pizzaiolo enum role should be allowed')

    # not allowed
    u3 = DummyUser('other')
    try:
        out = checker(current_user=u3)
        print('FAIL: role other should not be allowed')
    except HTTPException as e:
        print('PASS: role other correctly denied')


if __name__ == '__main__':
    run_tests()
