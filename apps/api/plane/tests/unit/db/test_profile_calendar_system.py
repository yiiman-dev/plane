# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

import pytest

from plane.app.serializers import ProfileSerializer
from plane.db.models import Profile, User

pytestmark = pytest.mark.unit


@pytest.fixture
def user(db):
    return User.objects.create(
        email="calendar-user@example.com",
        username="calendaruser",
        first_name="Cal",
        last_name="Endar",
        password="test-password-123",
    )


@pytest.mark.django_db
class TestProfileCalendarSystem:
    def test_defaults_to_gregorian(self, user):
        profile = Profile.objects.get(user=user)
        assert profile.calendar_system == Profile.CalendarSystem.GREGORIAN

    def test_is_exposed_by_the_serializer(self, user):
        data = ProfileSerializer(Profile.objects.get(user=user)).data
        assert "calendar_system" in data
        assert data["calendar_system"] == "gregorian"

    def test_can_be_set_to_persian(self, user):
        profile = Profile.objects.get(user=user)
        profile.calendar_system = Profile.CalendarSystem.PERSIAN
        profile.save()
        assert Profile.objects.get(user=user).calendar_system == "persian"

    def test_round_trips_through_the_serializer(self, user):
        profile = Profile.objects.get(user=user)
        serializer = ProfileSerializer(profile, data={"calendar_system": "persian"}, partial=True)
        assert serializer.is_valid(), serializer.errors
        serializer.save()
        assert Profile.objects.get(user=user).calendar_system == "persian"

    def test_rejects_an_unknown_system(self, user):
        profile = Profile.objects.get(user=user)
        serializer = ProfileSerializer(profile, data={"calendar_system": "mayan"}, partial=True)
        assert not serializer.is_valid()
        assert "calendar_system" in serializer.errors
