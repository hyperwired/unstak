# UNSTAK_START ---------------------------------------------------------------------------------------------------------
#
# unstak, an alternative balancing method for minqlx created by github/hyperwired aka "stakz", 2016-07-31
# This code is released under the MIT Licence:
#
# The MIT License (MIT)
#
# Copyright (c) 2016
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
# ----------------------------------------------------------------------------------------------------------------------
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


class PerformanceSnapshot(object):
    def __init__(self, elo, elo_variance):
        self._elo = elo
        self._elo_variance = elo_variance

    @property
    def elo(self):
        return self._elo

    @property
    def elo_variance(self):
        return self._elo_variance

    def desc(self):
        return "elo=%s (~%s)" % (self._elo, self._elo_variance)

    def __str__(self):
        return format_obj_desc_str(self)

    def __repr__(self):
        return format_obj_desc_repr(self)


class PerformanceHistory(object):
    def __init__(self):
        self._snapshots = []

    def has_data(self):
        return len(self._snapshots)

    def latest_snapshot(self):
        if self.has_data():
            return self._snapshots[-1]
        return None

    def desc(self):
        latest = self.latest_snapshot()
        if latest:
            return "%s, history=%s" % (latest.desc(), len(self._snapshots))
        return "<empty>"

    def __str__(self):
        return format_obj_desc_str(self)

    def __repr__(self):
        return format_obj_desc_repr(self)


class PlayerInfo(object):
    def __init__(self, name=None, perf_history=None, steam_id=None, ext_obj=None):
        self._name = name
        self._perf_history = perf_history
        self._steam_id = steam_id
        self._ext_obj = ext_obj

    @property
    def steam_id(self):
        return self._steam_id

    @property
    def ext_obj(self):
        return self._ext_obj

    @property
    def perf_history(self):
        return self._perf_history

    @property
    def latest_perf(self):
        return self._perf_history.latest_snapshot()

    @property
    def elo(self):
        return self.latest_perf.elo

    @property
    def elo_variance(self):
        return self.latest_perf.elo_variance

    @property
    def name(self):
        return self._name

    def desc(self):
        return "'%s': %s" % (self._name, self._perf_history.desc())

    def __str__(self):
        return format_obj_desc_str(self)

    def __repr__(self):
        return format_obj_desc_repr(self)


def player_info_list_from_steam_id_name_ext_obj_elo_dict(d):
    out = []
    for steam_id, (name, elo, ext_obj) in d.items():
        perf_snap = PerformanceSnapshot(elo, 0)
        perf_history = PerformanceHistory()
        perf_history._snapshots.append(perf_snap)
        player_info = PlayerInfo(name, perf_history, steam_id=steam_id, ext_obj=ext_obj)
        out.append(player_info)
    return out


class FixedSizePriorityQueue(object):
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


class PlayerStats(object):
    def __init__(self, player):
        self.player = player
        self.relative_deviation = 0

    @property
    def relative_deviation_category(self):
        if self.relative_deviation < 0:
            return math.ceil(self.relative_deviation)
        return math.floor(self.relative_deviation)


class TeamStats(object):
    def __init__(self, team_players):
        self.players = team_players

    def get_elo_list(self, player_stats_dict):
        return [player_stats_dict[pid].player.elo for pid in self.players]

    def combined_skill_rating(self, player_stats_dict):
        return sum(self.get_elo_list(player_stats_dict))

    def skill_rating_stdev(self, player_stats_dict):
        return calc_standard_deviation(self.get_elo_list(player_stats_dict))



class SingleTeamBakedStats(object):
    def __init__(self):
        self.skill_rating_sum = 0
        self.skill_rating_mean = 0
        self.skill_rating_stdev = 0
        self.num_players = 0
        self.players_by_stdev_rel_server_dict = {}
        self.players_by_speed_rel_server_dict = {}


class MatchPrediction(object):
    def __init__(self):
        self.team_a = SingleTeamBakedStats()
        self.team_b = SingleTeamBakedStats()
        self.bias = 0
        self.distance = 0
        self.confidence = 0

    def describe_prediction_short(self, team_names=None):
        # assuming bias is in the interval [-1,1], convert it to favoured chance so that
        # a bias of zero gets presented as a 50%/50% win prediction
        left_team_desc = ""
        right_team_desc = ""
        if team_names:
            assert len(team_names) == 2
            left_team_desc = "%s " % team_names[0]
            right_team_desc = " %s" % team_names[1]

        right_win_chance = self.bias * 100
        left_win_chance = 100 - right_win_chance
        return "%s%.2f%%/%.2f%%%s" % (left_team_desc, left_win_chance, right_win_chance, right_team_desc)

    def get_desc(self):
        raise NotImplementedError


def generate_match_prediction(team_a_baked, team_b_baked):
    assert isinstance(team_a_baked, SingleTeamBakedStats)
    assert isinstance(team_b_baked, SingleTeamBakedStats)
    prediction = MatchPrediction()
    prediction.team_a = team_a_baked
    prediction.team_b = team_b_baked
    prediction.bias = (1.0 * team_b_baked.skill_rating_sum) / (team_a_baked.skill_rating_sum + team_b_baked.skill_rating_sum)
    prediction.distance = (0.5 - prediction.bias)
    return prediction


class BalancePrediction(object):
    def __init__(self, team_a, team_b):
        self.team_a_stats = TeamStats(team_a)
        self.team_b_stats = TeamStats(team_b)

    def generate_match_prediction(self, player_stats_dict):
        stats = []
        for team in [self.team_a_stats, self.team_b_stats]:
            bs = SingleTeamBakedStats()
            bs.skill_rating_sum = team.combined_skill_rating(player_stats_dict)
            bs.num_players = len(team.players)
            assert bs.num_players
            bs.skill_rating_mean = bs.skill_rating_sum/bs.num_players
            bs.skill_rating_stdev = team.skill_rating_stdev(player_stats_dict)
            stats.append(bs)
        return generate_match_prediction(*stats)


def nchoosek(n, r):
    return math.comb(n, r)


BalancedTeamCombo = collections.namedtuple("BalancedTeamCombo", ["teams_tup", "match_prediction"])


def player_ids_only(team):
    if team and isinstance(team[0], PlayerInfo):
        return [p.steam_id for p in team]
    return team


def player_names_and_skill_only(team):
    if team and isinstance(team[0], PlayerInfo):
        return " ".join(["%s(%s)" % (p.name, p.elo) for p in team])
    return team


def describe_balanced_team_combo(team_a, team_b, match_prediction):
    assert isinstance(match_prediction, MatchPrediction)
    return "Team A: %s | Team B: %s | outcome: %s" % (player_names_and_skill_only(team_a),
                                                      player_names_and_skill_only(team_b),
                                                      match_prediction.describe_prediction_short())


def _bake_team_stats(team_players):
    baked = SingleTeamBakedStats()
    baked.num_players = len(team_players)
    if not team_players:
        return baked
    elos = skill_rating_list(team_players)
    baked.skill_rating_sum = sum(elos)
    baked.skill_rating_mean = calc_mean(elos)
    baked.skill_rating_stdev = calc_standard_deviation(elos, mean=baked.skill_rating_mean) if len(elos) > 1 else 0
    return baked


def _shape_balance_score(team_a, team_b):
    # "Rank" here means the player's position inside their own team after sorting by elo:
    # rank 1 is the strongest player on that team, rank 2 is the next strongest, and so on.
    # We compare teams rank-by-rank after sorting by elo. This pushes the balancer toward
    # matching the overall shape of each roster instead of only equalizing team averages.
    # Example: a rank-1 player is compared with the other team's rank-1 player, rank-2 with
    # rank-2, etc. That is what helps avoid "one stacked top end plus weak anchors" teams.
    # The score is ordered from most important to least important:
    #   1. avoid any single badly mismatched rank pairing
    #   2. minimize the total weighted rank mismatch, with more weight on stronger players
    #   3. keep total elo close
    #   4. keep team spread / variance close
    sorted_team_a = sort_by_skill_rating_descending(team_a)
    sorted_team_b = sort_by_skill_rating_descending(team_b)
    rank_gaps = [abs(player_a.elo - player_b.elo) for player_a, player_b in zip(sorted_team_a, sorted_team_b)]
    weighted_gap = sum((len(rank_gaps) - index) * gap for index, gap in enumerate(rank_gaps))
    team_a_stats = _bake_team_stats(sorted_team_a)
    team_b_stats = _bake_team_stats(sorted_team_b)
    return (
        max(rank_gaps) if rank_gaps else 0,
        weighted_gap,
        abs(team_a_stats.skill_rating_sum - team_b_stats.skill_rating_sum),
        abs(team_a_stats.skill_rating_stdev - team_b_stats.skill_rating_stdev),
    )


def _team_signature(team):
    sorted_team = sort_by_skill_rating_descending(team)
    return tuple((player.elo, player.name or "", player.steam_id if player.steam_id is not None else -1)
                 for player in sorted_team)


def _candidate_key(team_a, team_b):
    return _shape_balance_score(team_a, team_b) + (_team_signature(team_a), _team_signature(team_b))


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


def balance_players_by_skill_distribution(players, verbose=False, max_results=None):
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
        raise ValueError("balance_players_by_skill_distribution requires an even number of players")

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
        if verbose:
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
            match_prediction = generate_match_prediction(_bake_team_stats(team_a), _bake_team_stats(team_b))
            print("Combo %d : %s" % (mask + 1, describe_balanced_team_combo(team_a, team_b, match_prediction)))

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
        match_prediction = generate_match_prediction(_bake_team_stats(teams[0]), _bake_team_stats(teams[1]))
        result_combos.append(BalancedTeamCombo(teams_tup=teams, match_prediction=match_prediction))
    return result_combos


def balance_players_by_skill_variance(players, verbose=False, prune_search_space=True, max_results=None):
    return balance_players_by_skill_distribution(players, verbose=verbose, max_results=max_results)


SwitchOperation = collections.namedtuple("SwitchOperation", ["players_affected",
                                                             "players_moved_from_a_to_b", "players_moved_from_b_to_a"])

SwitchProposal = collections.namedtuple("SwitchProposal", ["switch_operation", "balanced_team_combo"])


def get_proposed_team_combo_moves(team_combo_1, team_combo_2):
    # team_combo_1 is current, team_combo_2 is a proposed combination
    assert len(team_combo_1) == 2 and len(team_combo_2) == 2
    team1a, team1b = set(team_combo_1[0]), set(team_combo_1[1])
    if isinstance(team_combo_2, BalancedTeamCombo):
        team2a, team2b = set(team_combo_2.teams_tup[0]), set(team_combo_2.teams_tup[1])
    else:
        team2a, team2b = set(team_combo_2[0]), set(team_combo_2[1])
    assert team1a.union(team1b) == team2a.union(team2b), "inconsistent input data"
    assert not team1a.intersection(team1b), "inconsistent input data"
    assert not team2a.intersection(team2b), "inconsistent input data"
    players_moved_from_a_to_b = team2a.difference(team1a)
    players_moved_from_b_to_a = team2b.difference(team1b)
    players_affected = players_moved_from_a_to_b.union(players_moved_from_b_to_a)
    return SwitchOperation(players_affected=players_affected,
                           players_moved_from_a_to_b=players_moved_from_a_to_b,
                           players_moved_from_b_to_a=players_moved_from_b_to_a)


def describe_switch_operation(switch_op, team_names=None):
    assert isinstance(switch_op, SwitchOperation)
    left_team_desc = ""
    right_team_desc = ""
    if team_names:
        assert len(team_names) == 2
        left_team_desc = "%s " % team_names[0]
        right_team_desc = " %s" % team_names[1]

    def get_names(player_set):
        s = []
        for i, player in enumerate(sorted(list(player_set), key=lambda p: p.elo, reverse=True)):
            if i != 0:
                s.append(", ")
            s.append("%s(%d)" % (player.name, player.elo))
        return "".join(s)

    out = []
    if switch_op.players_moved_from_a_to_b:
        out.append("%s --->%s" % (get_names(switch_op.players_moved_from_a_to_b), right_team_desc))
    if switch_op.players_moved_from_a_to_b and switch_op.players_moved_from_b_to_a:
        out.append(" | ")
    if switch_op.players_moved_from_b_to_a:
        out.append("%s<--- %s" % (left_team_desc, get_names(switch_op.players_moved_from_b_to_a)))
    return "".join(out)


def generate_switch_proposals(teams, verbose=False, max_results=5):
    # add 1 to max results, because if the input teams are optimal, then they will come as a result.
    players = []
    [[players.append(p) for p in team_players] for team_players in teams]
    balanced_team_combos = balance_players_by_skill_variance(players,
                                                             verbose=verbose,
                                                             prune_search_space=True,
                                                             max_results=max_results+1)
    switch_proposals = []
    for balanced_combo in balanced_team_combos:
        switch_op = get_proposed_team_combo_moves(teams, balanced_combo)
        assert isinstance(switch_op, SwitchOperation)
        assert isinstance(balanced_combo, BalancedTeamCombo)
        if not switch_op.players_affected:
            # no change
            continue
        switch_proposals.append(SwitchProposal(switch_operation=switch_op, balanced_team_combo=balanced_combo))

    return switch_proposals


class Unstaker(object):
    """
    This class encapsulates a set of unstak balancing suggestions, and data related to current server
    operations on these suggestions. It can be seen as a finite state machine managing these steps:

        - STARTGEN: Invalidation of old suggestions. (e.g. vote enacted, teams change, new match).
        - GENERATING: Generation of new suggestions (possibly a long running operation).
        - STOREGEN: Recording the generated results (multiple choices of balancing)
        - PRESENTGEN: Presentation of the group of suggestions, ready for selection.
        - VOTECHOICE: Accepting democratic player votes for selecting the balance suggestion.
                      (It can be forced by admin).
        - RESETCHOICE: An admin nominated transition from VOTECHOICE to PRESENTGEN. 
                       (not part of the standard flow).
        - PLAYERCONFIRMATION: Waiting for nominated switch players to confirm unanimous agreement.
                              (It can be forced by admin).
        - EXECUTESWITCH: Perform the swap action. After this we are back at STARTGEN.

    When PRESENTGEN occurs, the options are listed in descending order of predicted fitness.
    In other words, the calculated best balanced option is presented first.

    A natural consequence of this structure is that we can encode an admin forced balance operation 
    ("unstak") as a forced progression through all FSM steps assuming all players voted the first
    choice in VOTECHOICE, followed by all players agreeing in PLAYERCONFIRMATION. So a balance operation
    can simply set a bit that auto progresses through all states.

    There are a few complexities to bear in mind when thinking about unstak balancing compared to the
    existing balance operation:
        - unstak will try to balance mismatched odd-even teams (n vs n+1). 
            - legacy balance will only attempt to balance teams with matching player counts (n vs n).
        - unstak can suggest player switches that can involve a single player or up to half of all players.
            - legacy balance will only suggest a switch between player pairs.
        - unstak tries to match "skill distribution shape" of the teams, and not just aggregated values.
            - legacy balance can consider a fully uniform team vs a highly skewed team as balanced, 
              unstak will not. 
            - As an example of a skewed vs uniform matching: Team A has 6 players around 1400 skillrating
              (normal distribution). Team B has players at [2200, 1950, 1800, 1100, 750, 600] skillratings.
              Both teams have the same skillrating average (1400) and sum. However, while Team B has a 
              chance of winning, the load on the top 3 players is large, due to the anchoring effect of
              the bottom 3 players on Team B. From experience, it can work, but it is most commonly a
              frustrating experience for all members of the skewed team, especially if Team A works together.
              Teamwork is a lot less effective for Team B due to skill disparity and focusing effects. 
              The "shape matching" property of unstak addresses this, but could be considered a disadvantage,
              because sometimes you can have interesting matches with skewed players, but this is rare.

    These differences are basically due to the fact that legacy balance uses a naive hill-climbing 
    style algorithm using player pair switches for iterative improvements (locally optimal solutions). 
    In contrast, unstak tries to completely re-assemble teams by first categorizing players based on 
    relative stat deviations, and then performing an exhaustive search between these categories and
    using a set of heuristics to keep the top N results. The search space is drastically reduced compared
    to a naive (N choose K) search by restricting to combinations which contain subsets of players in
    the same "skill deviation group" to be equally spread in a way that is non-consequetively biased 
    across adjacent deviation groups. This allows it to find a globally optimal solution (satisfying 
    the hueristic) in a smaller search space than a pure brute force that returns "shape matched" results.
    There is a very small chance that the heuristic-based global optimum lies outside of the trimmed
    search space, but that would probably be explained by a deficiency in the heuristic and would also
    probably represent a low quality match.

    Therefore, unstak is generally a more involved and expensive operation due to its exhaustive search approach 
    and may require being run as a delayed/background operation since it may take more than one frame to complete.
    """
    STARTGEN = 0
    GENERATING = 1
    STOREGEN = 2
    PRESENTGEN = 3
    VOTECHOICE = 4
    RESETCHOICE = 5
    PLAYERCONFIRMATION = 6
    EXECUTESWITCH = 7

    def __init__(self):
        self.state = self.STARTGEN
        self.switch_proposals = []
        self.current_switch_agreement = {}
        self.startgen_hash = None
        self.proposals_vote_choice = {}
        self.proposal_voted_player_ids = set()

    @classmethod
    def generate_startgen_hash(cls, players):
        """
        Fully deterministic value that makes it possible to do cheap equality checks to see if teams have changed. 
        """
        players_signature = set()
        for player in players:
            assert isinstance(player, PlayerInfo)
            players_signature.add((player.elo, player.elo_variance, player.team_name))
        return players_signature

# UNSTAK_END -----------------------------------------------------------------------------------------------------------
