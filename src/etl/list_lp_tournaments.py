"""Print candidate seed rows for lp_tournaments.csv — generate, then curate.

Usage: python src/etl/list_lp_tournaments.py 2024
Paste the output into data/seeds/lp_tournaments.csv and DELETE what you don't want.
"""

# import sys
# import time
# from lp_common import lp_login, with_backoff

# import leaguepedia_parser as lp

# REGIONS = ["Korea", "China", "EMEA", "Americas", "International", "Asia Pacific"]



# def main(year: int, regions: list[str]):
#     lp_login()
#     for region in regions:
#         tournaments = with_backoff(lp.get_tournaments, region, year=year)
#         for t in tournaments:
#             print(f"{region},{t.name},{year},")
#         time.sleep(15)

# if __name__ == "__main__":
#     year = int(sys.argv[1])
#     regions = sys.argv[2:] or REGIONS
#     main(year, regions)

from lp_common import lp_login
lp_login()
from leaguepedia_parser.site.leaguepedia import leaguepedia

for region in ["Asia Pacific", "Brazil"]:
    result = leaguepedia.query(
        tables="Tournaments",
        fields="Name, OverviewPage, Region, Year",
        where=f"Year='2025' AND Region='{region}'",
    )
    for r in result:
        print(f"{region},{r['Name']},2025,")