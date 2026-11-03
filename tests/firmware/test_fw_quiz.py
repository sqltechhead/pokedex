import random

from conftest import ENTRIES

from dex import state as s
from dex.index import Dex
from dex.quiz import Quiz
from dex.state import MENU, PokedexState


def make(seed: int = 1) -> Quiz:
    return Quiz(Dex(ENTRIES), random.Random(seed).randrange)


def test_four_different_choices_including_the_answer():
    quiz = make()
    for _ in range(50):
        assert len(set(quiz.choices)) == 4
        assert quiz.target in quiz.choices
        previous = quiz.target
        quiz.new_question()
        assert quiz.target != previous


def test_answer_is_not_always_first():
    quiz = make()
    places = set()
    for _ in range(40):
        places.add(quiz.choices.index(quiz.target))
        quiz.new_question()
    assert places == {0, 1, 2, 3}


def test_scoring():
    quiz = make()
    right = quiz.choices.index(quiz.target)
    assert quiz.choose(right)
    assert not quiz.choose((right + 1) % 4)  # already answered: ignored
    assert (quiz.score, quiz.asked) == (1, 1)
    quiz.new_question()
    assert not quiz.choose((quiz.choices.index(quiz.target) + 1) % 4)
    assert (quiz.score, quiz.asked) == (1, 2)


def test_quiz_screen_buttons():
    st = PokedexState(Dex(ENTRIES), rand=random.Random(3).randrange)
    st.open_menu(next(i for i, (_, view) in enumerate(MENU) if view == s.QUIZ))
    quiz = st.quiz
    while quiz.cursor != quiz.choices.index(quiz.target):
        st.handle(s.DOWN)
    st.handle(s.A)
    assert st.quiz_sound == "correct" and quiz.score == 1
    first = quiz.target
    st.handle(s.A)  # next question
    assert not quiz.answered and quiz.target != first
    st.handle(s.B)
    assert st.view == s.HOME
