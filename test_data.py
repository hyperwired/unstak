import random
import math
import unittest
import itertools
from balancer_unstak import *
import collections

TEST_PLAYER_NAMES = [
    "Alice", "Bob", "Carly", "Daniel", "Eugene", "Fred", "George", "Henry", "Ivan", "Julia", "Kim", "Lucy",
    "Mike", "Nathan", "Olivia", "Patricia", "Quentin", "Robert", "Sandra", "Thomas", "Ulric", "Vivian",
    "William", "Xavier", "Yuri", "Zachary"
]


def clamp(value, min_value=600, max_value=2700):
    return min(max(int(value), min_value), max_value)


def generate_player_set(num_players=10, random_elos=True):
    assert len(TEST_PLAYER_NAMES) >= num_players
    players = random.sample(TEST_PLAYER_NAMES, num_players)
    player_infos = []
    for player in players:
        elo = clamp(random.gauss(1400, 380), min_value=600, max_value=2700)
        elo_confidence = clamp(random.gauss(55, 40), min_value=20, max_value=150)
        perf_snap = PerformanceSnapshot(elo, elo_confidence)
        perf_history = PerformanceHistory()
        perf_history._snapshots.append(perf_snap)
        player_info = PlayerInfo(player, perf_history)
        player_infos.append(player_info)

    return player_infos


def generate_player_info_list_from_elos(player_elos):
    d = {}
    for i, elo in enumerate(player_elos):
        assert i < len(TEST_PLAYER_NAMES)
        d[i] = (TEST_PLAYER_NAMES[i], elo, None)
    return player_info_list_from_steam_id_name_ext_obj_elo_dict(d)

ELOBalanceTestSet = collections.namedtuple("ELOBalanceTestSet", ["name", "input_elos", "team_a", "team_b"])


class ELOTestSetRegistry(object):
    GLOBAL_TESTS = collections.OrderedDict()

    @classmethod
    def add_test(cls, test_set):
        assert isinstance(test_set, ELOBalanceTestSet)
        assert test_set.name not in cls.GLOBAL_TESTS
        cls.GLOBAL_TESTS[test_set.name] = test_set

    @classmethod
    def iter_tests(cls):
        for v in cls.GLOBAL_TESTS.values():
            yield v


def register_elo_test(test_set):
    ELOTestSetRegistry.add_test(test_set)

ELO_TEST_DATA = [
    ELOBalanceTestSet(name="Test01",
                      input_elos=[1841, 1616, 1402, 1401, 1395, 1368, 1170, 1091, 921, 816],
                      team_a=[1841, 1402, 1395, 1091, 816],
                      team_b=[1616, 1401, 1368, 1170, 921]),

    ELOBalanceTestSet(name="Test02",
                      input_elos=[2150, 1640, 1600, 1212, 929],
                      team_a=[2150, 1600],
                      team_b=[1640, 1212, 929]),

    ELOBalanceTestSet(name="Test03",
                      input_elos=[2290, 2249, 2073, 2045, 2025, 2019, 1993, 1843, 1691, 1600, 1585, 1532, 1493, 1493, 1437, 1337],
                      team_a=[2073, 2045, 2025, 2019, 1585, 1532, 1493, 1493],
                      team_b=[2290, 2249, 1993, 1843, 1691, 1600, 1437, 1337]),

    ELOBalanceTestSet(name="Test04",
                      input_elos=[2249, 1993, 1941, 1930, 1836, 1689, 1626, 1574, 1493, 1493, 1473, 1176],
                      team_a=[1941, 1836, 1689, 1626, 1574, 1493],
                      team_b=[2249, 1993, 1930, 1493, 1473, 1176]),

    ELOBalanceTestSet(name="Test05",
                      input_elos=[2216, 1984, 1942, 1682, 1589, 1543, 1469, 1337, 1252, 1200, 950, 948, 871, 627],
                      team_a=[1942, 1589, 1543, 1337, 1252, 1200, 948],
                      team_b=[2216, 1984, 1682, 1469, 950, 871, 627])

]

for ELO_TEST in ELO_TEST_DATA:
    ELOTestSetRegistry.add_test(ELO_TEST)


def sorted_elos(team):
    return tuple(sorted(team, reverse=True))


def iter_even_sized_tests():
    for test_set in ELOTestSetRegistry.iter_tests():
        if len(test_set.input_elos) % 2 == 0:
            yield test_set


def balance_score_from_elos(team_a, team_b):
    team_a = sorted_elos(team_a)
    team_b = sorted_elos(team_b)
    rank_gaps = [abs(player_a - player_b) for player_a, player_b in zip(team_a, team_b)]

    def stdev(values):
        mean = sum(values) / float(len(values))
        return math.sqrt(sum((value - mean) ** 2 for value in values) / len(values))

    return (
        max(rank_gaps) if rank_gaps else 0,
        sum((len(rank_gaps) - index) * gap for index, gap in enumerate(rank_gaps)),
        abs(sum(team_a) - sum(team_b)),
        abs(stdev(team_a) - stdev(team_b)),
    )


def reference_balance_elos(player_elos):
    sorted_players = sorted_elos(player_elos)
    team_size = len(sorted_players) // 2
    anchor_player = sorted_players[0]
    remaining_players = sorted_players[1:]
    best_candidate = None

    for combo_indexes in itertools.combinations(range(len(remaining_players)), team_size - 1):
        combo_index_set = set(combo_indexes)
        team_a = (anchor_player,) + tuple(remaining_players[index] for index in combo_indexes)
        team_b = tuple(remaining_players[index] for index in range(len(remaining_players)) if index not in combo_index_set)
        teams = (sorted_elos(team_a), sorted_elos(team_b))
        candidate = (balance_score_from_elos(*teams), teams)
        if best_candidate is None or candidate < best_candidate:
            best_candidate = candidate

    return best_candidate[1]


def single_elo_test(test_case, **kwargs):
    assert isinstance(test_case, ELOBalanceTestSet)
    test_name, elos, expected_a, expected_b = test_case
    players = generate_player_info_list_from_elos(elos)
    balanced_team_combos = balance_players_by_skill_variance(players, **kwargs)
    balanced_teams = balanced_team_combos[0].teams_tup
    balanced_elos = tuple(sorted_elos(player.elo for player in team) for team in balanced_teams)
    return balanced_elos, reference_balance_elos(elos)


class UnstakBalanceTest(unittest.TestCase):
    def test_elo_balancing_matches_reference_search(self):
        for test_set in iter_even_sized_tests():
            balanced_elos, reference_elos = single_elo_test(test_set, max_results=1)
            self.assertEqual({tuple(balanced_elos[0]), tuple(balanced_elos[1])},
                             {tuple(reference_elos[0]), tuple(reference_elos[1])},
                             test_set.name)

    def test_balancer_is_input_order_insensitive(self):
        rng = random.Random(7)
        for test_set in iter_even_sized_tests():
            reference_elos = reference_balance_elos(test_set.input_elos)
            for _ in range(5):
                shuffled_elos = list(test_set.input_elos)
                rng.shuffle(shuffled_elos)
                players = generate_player_info_list_from_elos(shuffled_elos)
                balanced_team_combos = balance_players_by_skill_variance(players, max_results=1)
                balanced_teams = balanced_team_combos[0].teams_tup
                balanced_elos = tuple(sorted_elos(player.elo for player in team) for team in balanced_teams)
                self.assertEqual({tuple(balanced_elos[0]), tuple(balanced_elos[1])},
                                 {tuple(reference_elos[0]), tuple(reference_elos[1])},
                                 test_set.name)

    def test_balancer_prefers_distribution_matching(self):
        uniform_team = (1450, 1425, 1410, 1390, 1380, 1360)
        skewed_team = (2200, 1950, 1800, 1100, 750, 600)
        player_elos = uniform_team + skewed_team
        balanced_teams = reference_balance_elos(player_elos)
        self.assertLess(balance_score_from_elos(*balanced_teams),
                        balance_score_from_elos(uniform_team, skewed_team))


def run_tests():
    pass

if __name__ == '__main__':
    unittest.main()
