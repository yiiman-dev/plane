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


@pytest.fixture
def profile(user):
    # No signal creates a Profile alongside a User — the two are independent records, and the only
    # production call sites are the signup adapter and the license admin view. A bare
    # `User.objects.create` therefore leaves the user with no Profile, so the fixture has to make
    # one explicitly for `Profile.objects.get(user=...)` to resolve.
    return Profile.objects.create(user=user)


@pytest.mark.django_db
class TestProfileCalendarSystem:
    def test_defaults_to_gregorian(self, profile):
        assert profile.calendar_system == Profile.CalendarSystem.GREGORIAN

    def test_is_exposed_by_the_serializer(self, profile):
        data = ProfileSerializer(profile).data
        assert "calendar_system" in data
        assert data["calendar_system"] == "gregorian"

    def test_can_be_set_to_persian(self, profile):
        profile.calendar_system = Profile.CalendarSystem.PERSIAN
        profile.save()
        assert Profile.objects.get(user=profile.user).calendar_system == "persian"

    def test_round_trips_through_the_serializer(self, profile):
        serializer = ProfileSerializer(profile, data={"calendar_system": "persian"}, partial=True)
        assert serializer.is_valid(), serializer.errors
        serializer.save()
        assert Profile.objects.get(user=profile.user).calendar_system == "persian"

    def test_rejects_an_unknown_system(self, profile):
        serializer = ProfileSerializer(profile, data={"calendar_system": "mayan"}, partial=True)
        assert not serializer.is_valid()
        assert "calendar_system" in serializer.errors


@pytest.fixture
def user_factory(db):
    """Build a fresh user + profile pair per test.

    The `user` fixture above reuses a single user, but `Profile.user` is a OneToOneField, so
    each creation-defaults test needs its own user.
    """

    def _create(slug: str, **profile_kwargs):
        owner = User.objects.create(
            email=f"{slug}@example.com",
            username=slug,
            first_name="Lang",
            last_name="Case",
            password="test-password-123",
        )
        return Profile.objects.create(user=owner, **profile_kwargs)

    return _create


@pytest.mark.django_db
class TestCalendarSystemDerivedFromLanguage:
    """The calendar is seeded from the interface language at Profile creation, once."""

    def test_fa_language_creates_persian(self, user_factory):
        profile = user_factory("cal-fa", language="fa")
        assert profile.calendar_system == Profile.CalendarSystem.PERSIAN

    def test_non_fa_language_creates_gregorian(self, user_factory):
        profile = user_factory("cal-en", language="en")
        assert profile.calendar_system == Profile.CalendarSystem.GREGORIAN

    def test_regional_fa_variant_creates_persian(self, user_factory):
        """The spec says "starts with fa", so fa-IR counts as Persian."""
        profile = user_factory("cal-fa-ir", language="fa-IR")
        assert profile.calendar_system == Profile.CalendarSystem.PERSIAN

    def test_language_change_after_creation_does_not_flip_calendar(self, user_factory):
        """The binding constraint: the derivation is creation-time only.

        Silently changing how an existing user's dates render is disruptive, so switching the
        interface language later must leave the calendar alone.
        """
        profile = user_factory("cal-switch", language="en")
        assert profile.calendar_system == Profile.CalendarSystem.GREGORIAN

        profile.language = "fa"
        profile.save()

        assert Profile.objects.get(pk=profile.pk).calendar_system == Profile.CalendarSystem.GREGORIAN

    def test_explicit_calendar_system_beats_derived_value(self, user_factory):
        """An explicit choice wins, including an explicit `gregorian` under a Persian language.

        "Caller did not choose" is expressed by the constructor keyword, not by the field value
        — see Profile.__init__. So a caller asking for gregorian gets gregorian.
        """
        profile = user_factory(
            "cal-explicit",
            language="fa",
            calendar_system=Profile.CalendarSystem.GREGORIAN,
        )
        assert profile.calendar_system == Profile.CalendarSystem.GREGORIAN

    def test_default_language_creates_gregorian(self, user_factory):
        """No language passed at all falls back to the field default, which is not Persian."""
        profile = user_factory("cal-default-lang")
        assert profile.calendar_system == Profile.CalendarSystem.GREGORIAN
