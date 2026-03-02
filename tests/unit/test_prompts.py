"""Unit tests for prompt templates."""

import pytest
from datetime import date, time

from src.conversation.prompts import build_system_prompt, build_greeting


class TestBuildSystemPrompt:
    def test_contains_restaurant_name(self):
        prompt = build_system_prompt(
            restaurant_name="Le Petit Bistro",
            reservation_date=date(2026, 4, 15),
            preferred_time=time(19, 30),
            party_size=4,
        )
        assert "Le Petit Bistro" in prompt

    def test_contains_party_size(self):
        prompt = build_system_prompt(
            restaurant_name="Test",
            reservation_date=date(2026, 4, 15),
            preferred_time=time(19, 30),
            party_size=6,
        )
        assert "6" in prompt

    def test_contains_function_names(self):
        prompt = build_system_prompt(
            restaurant_name="Test",
            reservation_date=date(2026, 4, 15),
            preferred_time=time(19, 30),
            party_size=4,
        )
        assert "confirm_reservation" in prompt
        assert "propose_alternative" in prompt
        assert "end_call" in prompt

    def test_with_flexibility(self):
        prompt = build_system_prompt(
            restaurant_name="Test",
            reservation_date=date(2026, 4, 15),
            preferred_time=time(19, 30),
            party_size=4,
            alt_time_start=time(18, 0),
            alt_time_end=time(21, 0),
        )
        assert "flexible" in prompt.lower() or "Flexibility" in prompt
        assert "06:00 PM" in prompt or "6:00 PM" in prompt

    def test_without_flexibility(self):
        prompt = build_system_prompt(
            restaurant_name="Test",
            reservation_date=date(2026, 4, 15),
            preferred_time=time(19, 30),
            party_size=4,
        )
        assert "NO flexibility" in prompt

    def test_with_special_requests(self):
        prompt = build_system_prompt(
            restaurant_name="Test",
            reservation_date=date(2026, 4, 15),
            preferred_time=time(19, 30),
            party_size=4,
            special_requests="Window seat please",
        )
        assert "Window seat please" in prompt

    def test_without_special_requests(self):
        prompt = build_system_prompt(
            restaurant_name="Test",
            reservation_date=date(2026, 4, 15),
            preferred_time=time(19, 30),
            party_size=4,
        )
        assert "Special Requests" not in prompt


class TestBuildGreeting:
    def test_greeting_contains_details(self):
        greeting = build_greeting(
            restaurant_name="Le Petit Bistro",
            reservation_date=date(2026, 4, 15),
            preferred_time=time(19, 30),
            party_size=4,
        )
        assert "4" in greeting
        assert "7:30 PM" in greeting
        assert "April" in greeting

    def test_greeting_is_conversational(self):
        greeting = build_greeting(
            restaurant_name="Test",
            reservation_date=date(2026, 4, 15),
            preferred_time=time(19, 30),
            party_size=2,
        )
        # Should sound natural for a phone call
        assert "reservation" in greeting.lower() or "table" in greeting.lower()
