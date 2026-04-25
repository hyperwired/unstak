# -----------------------------------------------------------------------------------------------------------
# unstak: a collection of team balancing algorithms for minqlx created by github/hyperwired aka "stakz"
# This code is released under the MIT Licence:
#
# The MIT License (MIT)
#
# Copyright (c) 2016-2026 github/hyperwired
#
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in all
# copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
# SOFTWARE.
# -----------------------------------------------------------------------------------------------------------
import bisect
import collections
import itertools
import math

def format_obj_desc_str(obj):
    oclass = obj.__class__
    a = str(obj.__module__)
    b = str(obj.__class__.__name__)
    return "%s.%s %s" % (a, b, obj.desc())


def format_obj_desc_repr(obj):
    return "<%s object @ 0x%x>" % (format_obj_desc_str(obj), id(obj))


class PlayerInfo(object):
    __slots__ = ("_name", "_elo", "_elo_variance", "_steam_id", "_ext_obj")

    def __init__(self, name=None, elo=None, elo_variance=0, steam_id=None, ext_obj=None):
        self._name = name
        self._elo = elo
        self._elo_variance = elo_variance
        self._steam_id = steam_id
        self._ext_obj = ext_obj

    @property
    def steam_id(self):
        return self._steam_id

    @property
    def ext_obj(self):
        return self._ext_obj

    @property
    def latest_perf(self):
        return self

    @property
    def elo(self):
        return self._elo

    @property
    def elo_variance(self):
        return self._elo_variance

    @property
    def name(self):
        return self._name

    def desc(self):
        return "'%s': elo=%s (~%s)" % (self._name, self._elo, self._elo_variance)

    def __str__(self):
        return format_obj_desc_str(self)

    def __repr__(self):
        return format_obj_desc_repr(self)


def player_info_list_from_steam_id_name_ext_obj_elo_dict(d):
    out = []
    for steam_id, (name, elo, ext_obj) in d.items():
        player_info = PlayerInfo(name=name, elo=elo, elo_variance=0, steam_id=steam_id, ext_obj=ext_obj)
        out.append(player_info)
    return out


class FixedSizePriorityQueue(object):
    __slots__ = ("max_count", "items")

    def __init__(self, max_count):
        assert max_count
        self.max_count = max_count
        self.items = []

    def __len__(self):
        return len(self.items)

    def add_item(self, item):
        bisect.insort_right(self.items, item)
        if len(self.items) > self.max_count:
            self.items.pop()

    def nsmallest(self):
        return self.items[:self.max_count]


def sort_by_skill_rating_descending(players):
    return sorted(players, key=lambda p: (p.elo, p.name), reverse=True)


def skill_rating_list(players):
    return [p.elo for p in players]


def calc_mean(values):
    return sum(values)/(1.0*len(values))


def calc_standard_deviation(values, mean=None):
    if mean is None:
        mean = calc_mean(values)
    variance = calc_mean([(val - mean) ** 2 for val in values])
    return math.sqrt(variance)


BalancedTeamCombo = collections.namedtuple("BalancedTeamCombo", ["teams_tup", "balance_distance"])

# This module contains a collection of team balancing algorithms that try to match the "skill distribution shape" 
# of the teams instead of just their average skill rating. It tries to do this in a way that is:
# - Ordering-insensitive: the result is not biased to one team based on the input order of the player list.
# - Deterministic: the same input will generally always produce the same output
# - Aiming for optimal shape balance: the best possible match according to the shape-based score, within the constraints of the search space.
# - Not rigidly predictable: reduce the optics of inferable rules that players can easily learn and use to complain about the balance.
#
# What differentiates these algorithms is the search space they explore, and how long they take to run. 
# The most extreme approach is to check every possible split of the player list into two equal-sized teams, 
# but that is combinatorially explosive and not practical for live use at larger lobby sizes. 
# The strategies in this module are all designed to explore a reduced search space that still captures a variety of plausible 
# shape-matched splits while keeping the runtime manageable.
#
# -------------------------------------------------------------------------------------------------------------------------------
# If this sounds over-engineered, then here is a motivating example walking through an initial naive solution one might initially come up with:
# 1) Sort players decsending by elo and split them into two teams by alternating picks: team A gets ranks 1, 3, 5... and team B gets ranks 2, 4, 6...
# 2) Now the teams have a predictable "zig-zag" rank order where team A has the most skilled player and team B has the least skilled player. 
# 3) With this naive approach, Team A will generally beat Team B. So you already have introduced a bias and the teams are inherently unbalanced.
# 4) To try and improve that, you could try randomly swapping some players between the teams, but then you still need a way to evaluate how good the 
#   balance is, and know when to stop, and you might end up with a result that is worse than the original zig-zag split. You also might hit a local optimum
#   where you can't improve the shape by swapping any single pair of players, but you could improve it only by doing multiple swaps or swapping a group of 
#   players together.
# 5) Given this progression, you can see how this is a search problem: you have a large space of possible team splits, and you need to search through it 
# to find the best one, but also you need to be smart about how you search to avoid combinatorial explosion, and you need a scoring function to evaluate 
# the quality of each candidate split.
# 6) Add to this the additional constraint of matching the "shape" of the skill distribution of the teams, which means you want to compare 
# not just the average elo of the teams, but also how the players match up by rank within their teams. This has been shown to produce more 
# balanced and satisfying matches in practice, and certain real world test cases have been used to validate that the algorithms in this module are 
# producing better shape matches than the legacy average-based swapping approach.
# -------------------------------------------------------------------------------------------------------------------------------
#
# Balancing strategies in this module:
# - pairwise:
#   Sort by elo, split each adjacent pair, and only search the two orientations of each pair.
#   This is the simplest and most constrained local search. It is usually the easiest to reason
#   about and is fast enough for live use at full lobby sizes, but it is also the most predictable:
#   players can often infer that nearby ratings will always be separated.
#
# - quartets:
#   Sort by elo, group players into 4-player blocks, and search a small curated set of 2-vs-2
#   patterns inside each block. This reduces the "forced pair split" optics while keeping the
#   candidate count bounded. It is usually a better balance between readability, fairness optics,
#   and runtime than pairwise.
#
# - adaptive_blocks:
#   Like quartets, but the local block layout can mix 2-, 4-, and 6-player blocks based on gaps in
#   the sorted lobby. This gives the search more freedom around natural skill boundaries and often
#   produces the most flexible local-group result, but it adds more heuristics and more complexity
#   than the fixed-block approaches.
#
# - stddev_buckets:
#   Recreates the original unstak idea by bucketing players by relative deviation from the lobby
#   mean and then searching bucket-local splits. This tends to be the least predictable socially,
#   but it is also by far the slowest and least bounded strategy.
#
# Practical performance tradeoff:
# - pairwise, quartets, and adaptive_blocks are intended to stay live-usable even at 24 players.
#   In the latest benchmark run, representative 24-player cases came out around:
#     pairwise        10.490 ms (descending) / 21.405 ms (gaussian)
#     quartets         9.905 ms (descending) /  9.508 ms (gaussian)
#     adaptive_blocks 10.669 ms (descending) / 10.668 ms (gaussian)
# - stddev_buckets is dramatically slower. In the same 24-player cases it measured
#   9434.483 ms and 8508.686 ms, so it is better treated as an experimental / offline strategy
#   than a default live balancing choice for large lobbies.
BALANCE_STRATEGY_PAIRWISE = "pairwise"
BALANCE_STRATEGY_QUARTETS = "quartets"
BALANCE_STRATEGY_ADAPTIVE_BLOCKS = "adaptive_blocks"
BALANCE_STRATEGY_STDDEV_BUCKETS = "stddev_buckets"
BALANCE_STRATEGY_DEFAULT = BALANCE_STRATEGY_ADAPTIVE_BLOCKS


def _balance_distance(team_a, team_b):
    team_a_sum = sum(player.elo for player in team_a)
    team_b_sum = sum(player.elo for player in team_b)
    total = team_a_sum + team_b_sum
    if total == 0:
        return 0
    return abs(0.5 - ((1.0 * team_b_sum) / total))


def _team_signature(team):
    sorted_team = sort_by_skill_rating_descending(team)
    return tuple((player.elo, player.name or "", player.steam_id if player.steam_id is not None else -1)
                 for player in sorted_team)


def _pairwise_balance_score(team_a_sum, team_b_sum, team_a_sumsq, team_b_sumsq, team_size, max_gap, weighted_gap):
    team_a_mean = team_a_sum / float(team_size)
    team_b_mean = team_b_sum / float(team_size)
    team_a_variance = max((team_a_sumsq / float(team_size)) - (team_a_mean * team_a_mean), 0.0)
    team_b_variance = max((team_b_sumsq / float(team_size)) - (team_b_mean * team_b_mean), 0.0)
    return (
        max_gap,
        weighted_gap,
        abs(team_a_sum - team_b_sum),
        abs(math.sqrt(team_a_variance) - math.sqrt(team_b_variance)),
    )

def _build_local_group_options(group, local_patterns, team_size, rank_offset):
    group_options = []
    for option_index, (team_a_indexes, team_b_indexes) in enumerate(local_patterns):
        team_a_players = tuple(sorted((group[index] for index in team_a_indexes), key=lambda player: player.elo, reverse=True))
        team_b_players = tuple(sorted((group[index] for index in team_b_indexes), key=lambda player: player.elo, reverse=True))
        local_rank_gaps = tuple(abs(team_a_players[index].elo - team_b_players[index].elo)
                                for index in range(len(team_a_players)))
        weighted_gap = sum((team_size - (rank_offset + index)) * gap
                           for index, gap in enumerate(local_rank_gaps))
        group_options.append({
            "index": option_index,
            "team_a_players": team_a_players,
            "team_b_players": team_b_players,
            "team_a_sum": sum(player.elo for player in team_a_players),
            "team_b_sum": sum(player.elo for player in team_b_players),
            "team_a_sumsq": sum(player.elo * player.elo for player in team_a_players),
            "team_b_sumsq": sum(player.elo * player.elo for player in team_b_players),
            "max_gap": max(local_rank_gaps) if local_rank_gaps else 0,
            "weighted_gap": weighted_gap,
        })
    return tuple(group_options)


def _search_group_option_sets(group_option_sets, team_size, max_results):
    results = FixedSizePriorityQueue(max_results)

    for choice_tuple in itertools.product(*group_option_sets):
        team_a_sum = 0
        team_b_sum = 0
        team_a_sumsq = 0
        team_b_sumsq = 0
        max_gap = 0
        weighted_gap = 0
        choice_signature = []

        for option in choice_tuple:
            team_a_sum += option["team_a_sum"]
            team_b_sum += option["team_b_sum"]
            team_a_sumsq += option["team_a_sumsq"]
            team_b_sumsq += option["team_b_sumsq"]
            max_gap = max(max_gap, option["max_gap"])
            weighted_gap += option["weighted_gap"]
            choice_signature.append(option["index"])

        score = _pairwise_balance_score(
            team_a_sum, team_b_sum, team_a_sumsq, team_b_sumsq, team_size, max_gap, weighted_gap
        )
        results.add_item((score + (tuple(choice_signature),), choice_tuple))

    return results


def _materialize_group_option_results(results):
    result_combos = []
    for _, choice_tuple in results.nsmallest():
        team_a = []
        team_b = []
        for option in choice_tuple:
            team_a.extend(option["team_a_players"])
            team_b.extend(option["team_b_players"])
        teams = (tuple(team_a), tuple(team_b))
        result_combos.append(BalancedTeamCombo(teams_tup=teams, balance_distance=_balance_distance(teams[0], teams[1])))
    return result_combos


def balance_players_by_skill_distribution_pairwise(players, max_results=None):
    """
    Find the best equal-sized split by comparing the teams rank-by-rank instead of only by average elo.

    "Split" means one possible way of dividing the full player list into two equal-sized unlabeled
    teams. At this stage the teams are not yet "red" and "blue" - they are just the two halves of
    a candidate matchup.

    This implementation deliberately searches a reduced space: after sorting all players by elo, it
    forms adjacent pairs such as (rank 1, rank 2), (rank 3, rank 4), and so on, and only considers
    splits where each pair is split across the two teams. The search then only decides the
    orientation of each pair: which teammate from the pair goes to which side.

    The overall approach is:
      1. sort all players by elo
      2. build adjacent elo pairs and force each pair to be split across the two teams
      3. enumerate the 2^(n/2) possible pair orientations
      4. score each candidate by how well the two teams match by rank / shape
      5. return the best-scoring split(s)

    Compared with the exact search over all equal-size splits, this keeps the "shape matching"
    behavior while reducing the worst-case candidate count dramatically. For 24 players the exact
    split count is C(23, 11) = 1,352,078, while the pair-oriented search checks only 2^12 = 4,096
    candidates.

    "Rank" here means the player's position inside their own team after sorting by elo: rank 1 is
    the strongest player on that team, rank 2 is the next strongest, and so on. Because each
    adjacent input pair is split, a candidate's rank-1 matchup comes from the first pair, rank-2
    from the second pair, etc. That is what keeps the search focused on plausible shape-matched
    rosters instead of obviously skewed ones.

    The important difference from average-only balancing is that the score first tries to make the
    strongest players face similarly strong players, then the second-strongest face each other, and
    so on. Total elo still matters, but only after the rank distribution already looks sensible.

    Complexity note: the reduced search is O(2^(n/2) * n), which is still exponential, but much
    smaller than the previous combinatorial exact search. In practice that makes 24-player cases
    feasible inside a server-frame budget in Python, whereas the exact split enumeration was not.
    """
    if max_results is None:
        max_results = 1
    players = tuple(sort_by_skill_rating_descending(players))
    if not players:
        return []
    if len(players) % 2 != 0:
        raise ValueError("balance_players_by_skill_distribution_pairwise requires an even number of players")

    team_size = len(players) // 2
    pairs = [players[index:index + 2] for index in range(0, len(players), 2)]
    pair_elos = [(pair[0].elo, pair[1].elo) for pair in pairs]
    pair_gaps = [higher_elo - lower_elo for higher_elo, lower_elo in pair_elos]
    max_gap = max(pair_gaps) if pair_gaps else 0
    weighted_gap = sum((team_size - index) * gap for index, gap in enumerate(pair_gaps))
    results = FixedSizePriorityQueue(max_results)

    for mask in range(1 << team_size):
        team_a_sum = 0
        team_b_sum = 0
        team_a_sumsq = 0
        team_b_sumsq = 0
        mask_bits = mask

        for higher_elo, lower_elo in pair_elos:
            if mask_bits & 1:
                team_a_elo, team_b_elo = lower_elo, higher_elo
            else:
                team_a_elo, team_b_elo = higher_elo, lower_elo
            mask_bits >>= 1

            team_a_sum += team_a_elo
            team_b_sum += team_b_elo
            team_a_sumsq += team_a_elo * team_a_elo
            team_b_sumsq += team_b_elo * team_b_elo

        score = _pairwise_balance_score(
            team_a_sum, team_b_sum, team_a_sumsq, team_b_sumsq, team_size, max_gap, weighted_gap
        )
        results.add_item((score + (mask,), mask))

    result_combos = []
    for _, mask in results.nsmallest():
        team_a = []
        team_b = []
        mask_bits = mask
        for higher_player, lower_player in pairs:
            if mask_bits & 1:
                team_a_player, team_b_player = lower_player, higher_player
            else:
                team_a_player, team_b_player = higher_player, lower_player
            mask_bits >>= 1
            team_a.append(team_a_player)
            team_b.append(team_b_player)
        teams = (tuple(team_a), tuple(team_b))
        result_combos.append(BalancedTeamCombo(teams_tup=teams, balance_distance=_balance_distance(teams[0], teams[1])))
    return result_combos


def balance_players_by_skill_distribution_quartets(players, max_results=None):
    """
    Reduced local-group search using 4-player blocks. Each quartet contributes two players to each
    side using a small set of plausible 2-vs-2 patterns, and if the total player count is not
    divisible by 4 the final leftover pair is split 1-vs-1.

    For 24 players this checks 4^6 = 4,096 quartet orientations, which keeps the search in the same
    order of magnitude as the pairwise strategy while relaxing the visible "adjacent pair must split"
    rule.
    """
    if max_results is None:
        max_results = 1
    players = tuple(sort_by_skill_rating_descending(players))
    if not players:
        return []
    if len(players) % 2 != 0:
        raise ValueError("balance_players_by_skill_distribution_quartets requires an even number of players")

    team_size = len(players) // 2
    raw_groups = [players[index:index + 4] for index in range(0, len(players), 4)]
    group_option_sets = []
    rank_offset = 0

    for group in raw_groups:
        if len(group) == 4:
            # Allowed quartet patterns are intentionally a small curated subset rather than all
            # 2-vs-2 combinations. They all keep the very top player in the block separated from
            # the second-best player, but still allow multiple plausible ways to distribute the
            # remaining strength inside the block.
            #
            # Using only a few local patterns keeps the search cheap enough to enumerate while
            # avoiding the very rigid "adjacent pair must always split" rule from the pairwise
            # strategy. In practice this gives each 4-player block a couple of different shapes:
            # "outer vs inner" and "staggered" splits, plus their mirrored orientations.
            local_patterns = (
                ((0, 3), (1, 2)),
                ((1, 2), (0, 3)),
                ((0, 2), (1, 3)),
                ((1, 3), (0, 2)),
            )
        elif len(group) == 2:
            # If the player count is not divisible by 4, the final leftover pair is handled like a
            # tiny block with only the two mirrored 1-vs-1 orientations.
            local_patterns = (
                ((0,), (1,)),
                ((1,), (0,)),
            )
        else:
            raise ValueError("Quartet strategy only supports groups of 4 plus an optional final pair")

        # Each local option is pre-scored so the global search only has to combine block-level
        # summaries instead of rebuilding the full shape score from scratch every time.
        group_option_sets.append(_build_local_group_options(group, local_patterns, team_size, rank_offset))
        rank_offset += len(group) // 2

    results = _search_group_option_sets(group_option_sets, team_size, max_results)
    return _materialize_group_option_results(results)


def _iter_adaptive_group_size_layouts(total_players):
    if total_players == 0:
        yield ()
        return
    for group_size in (2, 4, 6):
        if total_players >= group_size:
            for remainder_layout in _iter_adaptive_group_size_layouts(total_players - group_size):
                yield (group_size,) + remainder_layout


def _median_value(values):
    sorted_values = sorted(values)
    middle = len(sorted_values) // 2
    if len(sorted_values) % 2:
        return sorted_values[middle]
    return (sorted_values[middle - 1] + sorted_values[middle]) / 2.0


def _percentile_value(values, percentile):
    sorted_values = sorted(values)
    index = int(round((len(sorted_values) - 1) * percentile))
    return sorted_values[index]


def _derive_adaptive_layout_penalties(players):
    adjacent_gaps = [players[index].elo - players[index + 1].elo for index in range(len(players) - 1)]
    if not adjacent_gaps:
        return 1.0, 1.0

    median_gap = _median_value(adjacent_gaps)
    upper_quartile_gap = _percentile_value(adjacent_gaps, 0.75)
    cut_penalty = max(1.0, upper_quartile_gap)
    # Two-player blocks are intentionally discouraged a bit more than ordinary cuts so the adaptive
    # layout does not collapse back into the pairwise strategy unless the lobby has unusually strong
    # local boundaries that justify it.
    pair_block_penalty = max(1.0, cut_penalty + (median_gap * 0.5))
    return cut_penalty, pair_block_penalty


def _choose_adaptive_group_sizes(players):
    cut_penalty, pair_block_penalty = _derive_adaptive_layout_penalties(players)
    best_layout = None
    best_key = None

    for layout in _iter_adaptive_group_size_layouts(len(players)):
        cut_score = 0
        boundary_index = 0
        for group_size in layout[:-1]:
            boundary_index += group_size
            cut_score += (players[boundary_index - 1].elo - players[boundary_index].elo) - cut_penalty
        layout_key = (
            cut_score - (layout.count(2) * pair_block_penalty),
            -layout.count(2),
            -len(layout),
            layout,
        )
        if best_key is None or layout_key > best_key:
            best_key = layout_key
            best_layout = layout
    return best_layout


def balance_players_by_skill_distribution_adaptive_blocks(players, max_results=None):
    """
    Adaptive local-group search using a mix of 2-, 4-, and 6-player blocks.

    The block layout is chosen first by looking for strong natural cut points in the sorted elo
    list. Larger gaps between adjacent players make better boundaries, while 2-player blocks are
    penalized so they are only used when the partitioning heuristic thinks they are justified.
    """
    if max_results is None:
        max_results = 1
    players = tuple(sort_by_skill_rating_descending(players))
    if not players:
        return []
    if len(players) % 2 != 0:
        raise ValueError("balance_players_by_skill_distribution_adaptive_blocks requires an even number of players")

    layout = _choose_adaptive_group_sizes(players)
    team_size = len(players) // 2
    group_option_sets = []
    rank_offset = 0
    player_index = 0

    for group_size in layout:
        group = players[player_index:player_index + group_size]
        player_index += group_size
        if group_size == 2:
            local_patterns = (
                ((0,), (1,)),
                ((1,), (0,)),
            )
        elif group_size == 4:
            local_patterns = (
                ((0, 3), (1, 2)),
                ((1, 2), (0, 3)),
                ((0, 2), (1, 3)),
                ((1, 3), (0, 2)),
            )
        elif group_size == 6:
            # Six-player blocks allow more local shapes than quartets, but still avoid the full set
            # of 3-vs-3 splits. These patterns focus on interleaved / staggered distributions so the
            # block can express several plausible rosters without collapsing into "top three versus
            # bottom three" style splits.
            local_patterns = (
                ((0, 3, 5), (1, 2, 4)),
                ((1, 2, 4), (0, 3, 5)),
                ((0, 3, 4), (1, 2, 5)),
                ((1, 2, 5), (0, 3, 4)),
                ((0, 2, 5), (1, 3, 4)),
                ((1, 3, 4), (0, 2, 5)),
                ((0, 2, 4), (1, 3, 5)),
                ((1, 3, 5), (0, 2, 4)),
            )
        else:
            raise ValueError("Unsupported adaptive block size: %s" % group_size)
        group_option_sets.append(_build_local_group_options(group, local_patterns, team_size, rank_offset))
        rank_offset += group_size // 2

    results = _search_group_option_sets(group_option_sets, team_size, max_results)
    return _materialize_group_option_results(results)


def balance_players_by_skill_stddev_buckets(players, prune_search_space=True, max_results=None):
    """
    Reimplementation of the original unstak idea: bucket players by their relative distance from the
    input pool mean, then only search bucket-local splits whose running team-size bias stays bounded
    as we move from strongest buckets to weakest buckets.
    """
    if max_results is None:
        max_results = 1
    players = tuple(sort_by_skill_rating_descending(players))
    if not players:
        return []
    if len(players) % 2 != 0:
        raise ValueError("balance_players_by_skill_stddev_buckets requires an even number of players")

    sample_mean = calc_mean(skill_rating_list(players))
    sample_stdev = calc_standard_deviation(skill_rating_list(players), mean=sample_mean)
    deviation_categories = collections.OrderedDict()
    for player in players:
        if sample_stdev == 0:
            relative_deviation = 0
        else:
            relative_deviation = (player.elo - sample_mean) / (sample_stdev * 1.0)
        deviation_category = int(math.ceil(relative_deviation) if relative_deviation < 0 else math.floor(relative_deviation))
        deviation_categories.setdefault(deviation_category, []).append(player)

    def generate_category_combo_sets(category_players):
        full_set = list(category_players)
        low_pick_count = len(full_set) // 2
        high_pick_count = len(full_set) - low_pick_count
        seen_splits = set()
        for pick_count in sorted(set((low_pick_count, high_pick_count))):
            for combo_indexes in itertools.combinations(range(len(full_set)), pick_count):
                combo_index_set = frozenset(combo_indexes)
                if combo_index_set in seen_splits:
                    continue
                seen_splits.add(combo_index_set)
                left_team = tuple(full_set[index] for index in combo_indexes)
                right_team = tuple(full_set[index] for index in range(len(full_set)) if index not in combo_index_set)
                yield (left_team, right_team)

    category_generators = [tuple(generate_category_combo_sets(category_players))
                           for category_players in deviation_categories.values()]

    def search_bucket_combos(use_pruning):
        results = FixedSizePriorityQueue(max_results)
        for combo_index, category_pick in enumerate(itertools.product(*category_generators)):
            running_delta = 0
            valid_combo = True
            for team_a_bucket, team_b_bucket in category_pick:
                category_delta = len(team_b_bucket) - len(team_a_bucket)
                if use_pruning and abs(category_delta) >= 2:
                    valid_combo = False
                    break
                running_delta += category_delta
                if use_pruning and abs(running_delta) >= 2:
                    valid_combo = False
                    break
            if not valid_combo:
                continue

            teams = tuple(tuple(itertools.chain.from_iterable(team)) for team in zip(*category_pick))
            if len(teams[0]) != len(teams[1]):
                continue
            balance_distance = _balance_distance(teams[0], teams[1])
            results.add_item(((balance_distance, _team_signature(teams[0]), _team_signature(teams[1])),
                              balance_distance,
                              teams))
        return results

    results = search_bucket_combos(prune_search_space)
    if len(results) == 0 and prune_search_space:
        results = search_bucket_combos(False)

    return [
        BalancedTeamCombo(teams_tup=teams, balance_distance=balance_distance)
        for _, balance_distance, teams in results.nsmallest()
    ]


def balance_players_by_skill_variance(players, prune_search_space=True, max_results=None,
                                      strategy=BALANCE_STRATEGY_DEFAULT):
    if strategy == BALANCE_STRATEGY_PAIRWISE:
        return balance_players_by_skill_distribution_pairwise(players, max_results=max_results)
    if strategy == BALANCE_STRATEGY_QUARTETS:
        return balance_players_by_skill_distribution_quartets(players, max_results=max_results)
    if strategy == BALANCE_STRATEGY_ADAPTIVE_BLOCKS:
        return balance_players_by_skill_distribution_adaptive_blocks(players, max_results=max_results)
    if strategy == BALANCE_STRATEGY_STDDEV_BUCKETS:
        return balance_players_by_skill_stddev_buckets(players,
                                                       prune_search_space=prune_search_space,
                                                       max_results=max_results)
    raise ValueError("Unknown balance strategy: %s" % strategy)



