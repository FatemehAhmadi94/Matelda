import pipeline

# labeling_budgets = [25, 49, 98, 196, 245, 294, 392, 490, 588, 686, 784, 882, 980, 1078, 1176, 1274, 1372, 1470, 1568, 1666, 1764, 1862, 1960]
labeling_budgets = [500, 1000, 2015,
 4030,
 6045,
 8060,
 10075,
 12090,
 14105,
 16120,
 18135,
 20150,
 22165,
 24180,
 26195,
 28210,
 30225,
 32240,
 34255,
 36270,
 38285,
 40300]
for labeling_budget in labeling_budgets:
    print(labeling_budget)
    pipeline.main(labeling_budget)