# unstak
skill balancing extension for multiplayer games

The gist is that it divides players into skill bands/buckets using standard deviation and then tries to balance those buckets across teams as a broad phase and then does a narrow phase pass to reduce the statistical elo difference, so both teams end up being "shaped" as similarly as possible so you dont get fang shuffles or heavily skewed teams that otherwise would have same overall average. 

It also tries to do this in a way that is not biased on order e.g. something naive like sorting by elos and then doing odd-even assignment always biases the team with the first picked (top elo) player. 

There is some test data that I took from real world balances where the elo avg was same but the teams were still screwed. 
