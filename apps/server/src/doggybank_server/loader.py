# Copyright 2026 DeepMind Technologies Limited
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#      http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
# Modified for Doggybank.


"""Loading games, and deciding which games the server can serve.

A game is served when it loads, its actions are integers, and every position
can be rebuilt from its history: replay and undo rebuild positions rather
than rewind them. Simultaneous-move games are served through OpenSpiel's
turn-based wrapper.
"""

import dataclasses
import functools
import types
from collections.abc import Mapping

import pyspiel
from absl import logging

import doggybank_engine.game  # noqa: F401  registers the poker games with pyspiel

# Imported to register the games written in Python.
from doggybank_server import (
    catalogue,
    contract,
    controllers,
    errors,
    information,
    loader_support,
    presenters,
)

_GameType = pyspiel.GameType

# The native dependency registers other games; only poker is served here.
SUPPORTED_GAMES = frozenset({"doggybank", "doggybank_acpc"})

# Re-exported: the session's parameters are part of what `load` reports.
session_parameters = loader_support.session_parameters


class UnknownGameError(errors.NotFoundError):
    """Raised when no game is registered under a name."""


class UnavailableError(errors.GameUnavailableError):
    """Raised when the server cannot serve a game, whatever its parameters."""


class InvalidParametersError(errors.BadRequestError):
    """Raised when a game refuses the parameters it is given."""


@dataclasses.dataclass(frozen=True)
class LoadedGame:
    """A loaded game and what the server needs to know to serve it.

    Attributes:
      name: The game's short name.
      parameters: The game's parameters, defaults included; read-only.
      game: The game as served: wrapped to be turn-based when `turn_based`.
      turn_based: Whether a simultaneous game is served through the turn-based
        wrapper.
      hides_information: Whether some player may not see the full state.
      provides_observation: Whether the game gives each player an observation
        string.
      provides_information_state: Whether the game gives each player an
        information state string.
    """

    name: str
    parameters: Mapping[str, contract.ParameterValue]
    game: pyspiel.Game
    turn_based: bool
    hides_information: bool
    provides_observation: bool
    provides_information_state: bool

    @property
    def num_seats(self) -> int:
        """The number of seats."""
        return int(self.game.num_players())

    @property
    def provides_struct(self) -> bool:
        """Whether the game's states serialize to structured JSON.

        Decided once per game and parameters, on first use, by
        `loader_support.struct_support`.
        """
        return self.struct_support(loader_support.StructKind.STATE)

    @property
    def provides_observation_struct(self) -> bool:
        """Whether the game gives each player a structured JSON observation.

        Decided once per game and parameters, on first use, by
        `loader_support.struct_support`.
        """
        return self.struct_support(loader_support.StructKind.OBSERVATION)

    def struct_support(self, kind: loader_support.StructKind) -> bool:
        """Whether the game provides the struct `kind`."""
        return loader_support.struct_support(
            kind,
            name=self.name,
            turn_based=self.turn_based,
            parameters=self.parameters,
            game=self.game,
        )

    @property
    def has_seat_views(self) -> bool:
        """Whether a seat can be shown the game without revealing hidden state."""
        return (
            not self.hides_information
            or self.provides_observation
            or self.provides_information_state
        )


@functools.cache
def registered_types() -> Mapping[str, pyspiel.GameType]:
    """Returns every served poker game's type, keyed by short name."""
    return {
        game_type.short_name: game_type
        for game_type in pyspiel.registered_games()
        if game_type.short_name in SUPPORTED_GAMES
    }


def unavailable_reason(game_type: pyspiel.GameType) -> str | None:
    """Returns why the server cannot serve a game of this type, or None."""
    if game_type.dynamics == _GameType.Dynamics.MEAN_FIELD:
        return "Mean-field games need a population distribution to play."
    if game_type.chance_mode == _GameType.ChanceMode.SAMPLED_STOCHASTIC:
        return (
            "Chance outcomes are sampled inside the state, so positions cannot "
            "be rebuilt from the history."
        )
    if game_type.action_structs_only:
        return "Actions are structures rather than integers."
    for name, default in game_type.parameter_specification.items():
        if not isinstance(default, (bool, int, float, str)):
            return f"Parameter {name!r} is a nested game, which cannot be set here."
    return None


def load(name: str, parameters: Mapping[str, contract.ParameterValue]) -> LoadedGame:
    """Loads a game with the given parameters.

    Args:
      name: A registered short name.
      parameters: Parameters to override; omitted ones take their defaults. An
        integer given for a real-valued parameter is widened.

    Returns:
      The loaded game.

    Raises:
      UnknownGameError: If no game is registered under `name`.
      UnavailableError: If the server cannot serve the game.
      InvalidParametersError: If the game refuses the parameters, or cannot
        build its initial state with them.
    """
    game_type = registered_types().get(name)
    if game_type is None:
        raise UnknownGameError(f"There is no game {name!r}.")
    reason = unavailable_reason(game_type)
    if reason is not None:
        raise UnavailableError(f"{name} cannot be served. {reason}")
    parameters = widen(game_type, parameters)
    base = load_or_refuse(name, parameters, turn_based=False)
    turn_based = game_type.dynamics == _GameType.Dynamics.SIMULTANEOUS
    game = load_or_refuse(name, parameters, turn_based=True) if turn_based else base
    new_initial_state(game, name)
    served_type = game.get_type()
    return LoadedGame(
        name=name,
        parameters=types.MappingProxyType(
            session_parameters(game_type, parameters, base.get_parameters())
        ),
        game=game,
        turn_based=turn_based,
        # Hidden if either the declared type or the type served (after
        # turn-based wrapping, which hides the moves made simultaneously) hides.
        hides_information=(
            information.hides_information(game_type) or information.hides_information(served_type)
        ),
        provides_observation=served_type.provides_observation_string,
        provides_information_state=(
            served_type.provides_information_state_string
            and name not in information.HIDDEN_DESPITE_DECLARATION
        ),
    )


def widen(
    game_type: pyspiel.GameType,
    parameters: Mapping[str, contract.ParameterValue],
) -> dict[str, contract.ParameterValue]:
    """Widens integers given for real-valued parameters, as JSON blurs them."""
    defaults = game_type.parameter_specification
    widened: dict[str, contract.ParameterValue] = {}
    for name, value in parameters.items():
        if (
            isinstance(defaults.get(name), float)
            and isinstance(value, int)
            and not isinstance(value, bool)
        ):
            widened[name] = float(value)
        else:
            widened[name] = value
    return widened


def load_or_refuse(
    name: str,
    parameters: Mapping[str, contract.ParameterValue],
    *,
    turn_based: bool,
) -> pyspiel.Game:
    """Loads a game, reporting its refusal as invalid parameters.

    What the game raised is logged, not sent: its text may name files or other
    details of the server.

    Args:
      name: A registered short name.
      parameters: The parameters to override; empty for the defaults.
      turn_based: Whether to load a simultaneous game through the turn-based
        wrapper.

    Returns:
      The loaded game.
    """
    try:
        if turn_based:
            return pyspiel.load_game_as_turn_based(name, dict(parameters))
        return pyspiel.load_game(name, dict(parameters))
    # Games refuse parameters with whatever exception their binding raises.
    except Exception as error:
        logging.info("%s refused the parameters %s: %s", name, dict(parameters), error)
        raise InvalidParametersError(
            f"{name} refuses these parameters; the server's log has the details."
        ) from error


def new_initial_state(game: pyspiel.Game, name: str) -> pyspiel.State:
    """Builds the initial state; some games check parameters only here.

    As when loading, what the game raised is logged, not sent.

    Args:
      game: The loaded game.
      name: The game's short name, for the log and the refusal.

    Returns:
      The game's initial state.
    """
    try:
        return game.new_initial_state()
    # As when loading, the exception's type depends on the game's binding.
    except Exception as error:
        logging.info("%s cannot start with its parameters: %s", name, error)
        raise InvalidParametersError(
            f"{name} cannot start with these parameters; the server's log has the details."
        ) from error


def build_catalogue() -> catalogue.Catalogue:
    """Returns the catalogue of every registered game, loading each once.

    Loading every game is slow, so what loading finds is cached for the life
    of the process. Each entry's `renderer` is not: it is read from the
    adapter registry on every call, so that an adapter registered or
    unregistered after the first call (`presenters.register`) is in the next
    catalogue.
    """
    return catalogue.Catalogue(
        games=tuple(
            dataclasses.replace(entry, renderer=renderer_of(entry)) for entry in loaded_entries()
        )
    )


def renderer_of(entry: catalogue.CatalogueEntry) -> str | None:
    """The renderer of `entry`'s adapter now; None when it has none."""
    if not entry.loadable:
        return None
    adapter = presenters.adapter_for(entry.name)
    return None if adapter is None else adapter.renderer


@functools.cache
def loaded_entries() -> tuple[catalogue.CatalogueEntry, ...]:
    """Every registered game's entry, loaded once; renderers are read later."""
    return tuple(catalogue_entry(game_type) for _, game_type in sorted(registered_types().items()))


def catalogue_entry(game_type: pyspiel.GameType) -> catalogue.CatalogueEntry:
    """Describes one game, loading it with its defaults to check it serves."""
    reason, loaded = default_availability(game_type)
    declared = catalogue.Information(game_type.information.name.lower())
    # A game served as hiding information is listed as of imperfect
    # information whatever its type declares, so that no client takes it
    # to hide nothing.
    if (
        declared == catalogue.Information.PERFECT_INFORMATION
        and loaded is not None
        and loaded.hides_information
    ):
        served_information = catalogue.Information.IMPERFECT_INFORMATION
    else:
        served_information = declared
    controller_names: tuple[str, ...]
    if loaded is None:
        controller_names = ()
    else:
        controller_names = tuple(
            controller.name for controller in controllers.available(loaded.game)
        )
    return catalogue.CatalogueEntry(
        name=game_type.short_name,
        long_name=game_type.long_name,
        dynamics=catalogue.Dynamics(game_type.dynamics.name.lower()),
        chance_mode=catalogue.ChanceMode(game_type.chance_mode.name.lower()),
        information=served_information,
        # A game type may declare no minimum (python_dynamic_routing declares
        # 0); a session has at least one seat.
        min_seats=max(1, game_type.min_num_players),
        max_seats=game_type.max_num_players,
        num_players=None if loaded is None else loaded.num_seats,
        parameters=parameter_specs(game_type),
        loadable=reason is None,
        unavailable_reason=reason,
        controllers=controller_names,
        # Read from the adapter registry by `build_catalogue`, on every call.
        renderer=None,
    )


def default_availability(
    game_type: pyspiel.GameType,
) -> tuple[str | None, LoadedGame | None]:
    """Returns why the default game cannot be served, or the game loaded.

    Args:
      game_type: A registered game type.

    Returns:
      The reason the game cannot be served with its defaults and None, or None
      and the game loaded with its defaults.
    """
    reason = unavailable_reason(game_type)
    if reason is None and not game_type.default_loadable:
        reason = "The game needs parameters to load."
    if reason is not None:
        return reason, None
    try:
        return None, load(game_type.short_name, {})
    except InvalidParametersError:
        return "The game does not load with its defaults.", None


# A parameter's type, from its default's Python type. The first match wins,
# and bool must come before int: True is an int in Python.
_PARAMETER_TYPES: tuple[
    tuple[type[bool] | type[int] | type[float] | type[str], catalogue.ParameterType], ...
] = (
    (bool, catalogue.ParameterType.BOOL),
    (int, catalogue.ParameterType.INT),
    (float, catalogue.ParameterType.FLOAT),
    (str, catalogue.ParameterType.STRING),
)


def parameter_specs(
    game_type: pyspiel.GameType,
) -> tuple[catalogue.ParameterSpec, ...]:
    """Describes the game's scalar parameters, ordered by name."""
    specs = []
    for name, default in sorted(game_type.parameter_specification.items()):
        parameter_type = next(
            (kind for python_type, kind in _PARAMETER_TYPES if isinstance(default, python_type)),
            None,
        )
        if parameter_type is None:
            # A nested game. `unavailable_reason` refuses every game that takes
            # one, so the catalogue lists such a game as unavailable and none of
            # its parameters is offered.
            continue
        specs.append(
            catalogue.ParameterSpec(
                name=name,
                type=parameter_type,
                kind=catalogue.ParameterKind.FREE,
                default=default,
                minimum=None,
                maximum=None,
                choices=None,
                description=None,
            )
        )
    return tuple(specs)
