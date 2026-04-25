from player_info import *
from balancer_unstak import *
import test_data


def ascii_line(n=80, c="-"):
    return n*c


def results_header(header):
    print ascii_line()
    print header


def print_team_stats(team_players):
    if not team_players:
        return
    player_count = len(team_players)
    total_elo = sum([i.elo for i in team_players])
    average_elo = total_elo/len(team_players)
    print "total elo = %s, average elo = %s" % (total_elo, average_elo)


def print_team(team_players, print_stats=True):
    for player in sort_by_skill_rating_descending(team_players):
        assert isinstance(player, PlayerInfo)
        print "%s:%s" % (player.name, player.latest_perf._elo)
    if print_stats:
        print_team_stats(team_players)


class TestPrinter(object):
    def team_average(self, team_players):
        """Calculates the average rating of a team."""
        total_elo = sum([i.elo for i in team_players])
        average_elo = total_elo / len(team_players)
        return average_elo

    def msg(self, s):
        print s

    def report_team_stats(self, new_blue_team, new_red_team):
        # print some stats
        avg_red = self.team_average(new_red_team)
        avg_blue = self.team_average(new_blue_team)
        diff_rounded = abs(round(avg_red) - round(avg_blue))  # Round individual averages.

        def team_color(team_index):
            return ""

        def stronger_team_index(red_amount, blue_amount):
            if red_amount > blue_amount:
                return 0
            if red_amount < blue_amount:
                return 1
            return None

        round_avg_red = round(avg_red)
        round_avg_blue = round(avg_blue)
        favoured_team_colour_prefix = team_color(stronger_team_index(round_avg_red, round_avg_blue))
        avg_msg = "{} vs {} - DIFFERENCE: {}".format(round_avg_red,
                                                                round_avg_blue,
                                                                favoured_team_colour_prefix,
                                                                diff_rounded)
        self.msg(avg_msg)


def print_teams(teams):
    team_a, team_b = teams
    print "team a: -------------"
    print_team(team_a)
    print "team b: -------------"
    print_team(team_b)
    TestPrinter().report_team_stats(team_a, team_b)


snap = PerformanceSnapshot(1600, 50)
print snap

#players = test_data.generate_player_set()
players = test_data.test_set_1()
print players
for player in players:
    print str(player)

_players = balance_players_random(players)
results_header("random")
print_teams(_players)

_players = balance_players_ranked_odd_even(players)
results_header("odd_even")
print_teams(_players)

_players = balance_players_by_skill_variance(players)
results_header("skill_variance")
print_teams(_players)
