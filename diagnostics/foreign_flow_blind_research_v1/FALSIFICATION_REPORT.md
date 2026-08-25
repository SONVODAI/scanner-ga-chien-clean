# Falsification Report

## FFB1_0001 — `net_pos` T10
- killed: `True` severity=`soft` reason=`depends_on_year_2009`
- survived_leave_top5: `False`
- survived_alt_horizon: `False`
  - {'test': 'leave_top5_symbols', 'removed': ['BVH', 'GAS', 'PTB', 'HHS', 'HPG'], 'incr': -0.0001623650400604203, 'survived': np.False_}
  - {'test': 'neighbor_horizons_same_sign', 'n_agree': 0, 'survived': False}
  - {'test': 'reverse_feature', 'reverse': 'net_neg', 'same_direction_effect': np.False_, 'rev_incr': -0.0016533697488451907}
  - {'test': 'drop_strongest_year', 'year': '2009', 'incr': -0.001779761001181092, 'survived': np.False_}

## FFB1_0002 — `net_neg` T3
- killed: `True` severity=`soft` reason=`depends_on_year_2011`
- survived_leave_top5: `True`
- survived_alt_horizon: `True`
  - {'test': 'leave_top5_symbols', 'removed': ['BVH', 'BMP', 'HAG', 'SBT', 'VHC'], 'incr': -0.0007957600031905266, 'survived': True}
  - {'test': 'neighbor_horizons_same_sign', 'n_agree': 3, 'survived': True}
  - {'test': 'reverse_feature', 'reverse': 'net_pos', 'same_direction_effect': np.False_, 'rev_incr': 0.0003422908375673555}
  - {'test': 'drop_strongest_year', 'year': '2011', 'incr': 0.00032298825036946525, 'survived': np.False_}

## FFB1_0003 — `net_neg` T5
- killed: `True` severity=`soft` reason=`depends_on_year_2011`
- survived_leave_top5: `True`
- survived_alt_horizon: `True`
  - {'test': 'leave_top5_symbols', 'removed': ['BVH', 'BMP', 'HAG', 'HSG', 'SBT'], 'incr': -0.0012149382785745662, 'survived': True}
  - {'test': 'neighbor_horizons_same_sign', 'n_agree': 3, 'survived': True}
  - {'test': 'reverse_feature', 'reverse': 'net_pos', 'same_direction_effect': np.False_, 'rev_incr': 0.0004943137964284101}
  - {'test': 'drop_strongest_year', 'year': '2011', 'incr': 0.0003190355957244475, 'survived': np.False_}

## FFB1_0004 — `net_neg` T10
- killed: `True` severity=`soft` reason=`depends_on_year_2011`
- survived_leave_top5: `True`
- survived_alt_horizon: `True`
  - {'test': 'leave_top5_symbols', 'removed': ['BMP', 'HAG', 'HSG', 'BVH', 'HHS'], 'incr': -0.0015347647148988748, 'survived': True}
  - {'test': 'neighbor_horizons_same_sign', 'n_agree': 3, 'survived': True}
  - {'test': 'reverse_feature', 'reverse': 'net_pos', 'same_direction_effect': np.False_, 'rev_incr': 0.0006787339959780242}
  - {'test': 'drop_strongest_year', 'year': '2011', 'incr': 0.0008531768063200194, 'survived': np.False_}

## FFB1_0005 — `net_zero` T10
- killed: `False` severity=`None` reason=`None`
- survived_leave_top5: `False`
- survived_alt_horizon: `False`
  - {'test': 'leave_top5_symbols', 'removed': ['PNJ', 'PTB', 'TCM', 'HCM', 'VOS'], 'incr': -0.000336141731898876, 'survived': np.False_}
  - {'test': 'neighbor_horizons_same_sign', 'n_agree': 0, 'survived': False}
  - {'test': 'drop_strongest_year', 'year': '2011', 'incr': 0.004777931838159915, 'survived': np.True_}

## FFB1_0006 — `streak_pos_ge3` T3
- killed: `False` severity=`None` reason=`None`
- survived_leave_top5: `False`
- survived_alt_horizon: `True`
  - {'test': 'leave_top5_symbols', 'removed': ['BVH', 'GAS', 'HHS', 'MSN', 'NTL'], 'incr': 0.00016036148072799065, 'survived': False}
  - {'test': 'neighbor_horizons_same_sign', 'n_agree': 3, 'survived': True}
  - {'test': 'reverse_feature', 'reverse': 'streak_neg_le_m3', 'same_direction_effect': np.False_, 'rev_incr': -0.0014402845975525504}
  - {'test': 'drop_strongest_year', 'year': '2009', 'incr': 0.00020414257233549815, 'survived': np.True_}
  - {'test': 'parent_condition', 'parent': 'net_pos', 'parent_incr': 0.0003422908375673555, 'ratio_parent_over_child': 0.39713279250794764}

## FFB1_0007 — `streak_pos_ge3` T5
- killed: `False` severity=`None` reason=`None`
- survived_leave_top5: `False`
- survived_alt_horizon: `True`
  - {'test': 'leave_top5_symbols', 'removed': ['BVH', 'GAS', 'KBC', 'MSN', 'DPM'], 'incr': 0.0004593820093522821, 'survived': False}
  - {'test': 'neighbor_horizons_same_sign', 'n_agree': 2, 'survived': True}
  - {'test': 'reverse_feature', 'reverse': 'streak_neg_le_m3', 'same_direction_effect': np.False_, 'rev_incr': -0.0027002782192419514}
  - {'test': 'drop_strongest_year', 'year': '2009', 'incr': 1.6477421379432417e-06, 'survived': np.True_}
  - {'test': 'parent_condition', 'parent': 'net_pos', 'parent_incr': 0.0004943137964284101, 'ratio_parent_over_child': 0.3823201994547471}

## FFB1_0008 — `streak_pos_ge3` T10
- killed: `True` severity=`soft` reason=`simpler_parent_explains`
- survived_leave_top5: `False`
- survived_alt_horizon: `True`
  - {'test': 'leave_top5_symbols', 'removed': ['BVH', 'KBC', 'GAS', 'HPG', 'PET'], 'incr': -0.0006228054543687975, 'survived': np.False_}
  - {'test': 'neighbor_horizons_same_sign', 'n_agree': 1, 'survived': True}
  - {'test': 'reverse_feature', 'reverse': 'streak_neg_le_m3', 'same_direction_effect': np.False_, 'rev_incr': -0.00449185492018393}
  - {'test': 'drop_strongest_year', 'year': '2010', 'incr': 0.004096642356358204, 'survived': np.True_}
  - {'test': 'parent_condition', 'parent': 'net_pos', 'parent_incr': 0.0006787339959780242, 'ratio_parent_over_child': 1.083836028747576}

## FFB1_0009 — `streak_neg_le_m3` T1
- killed: `False` severity=`None` reason=`None`
- survived_leave_top5: `False`
- survived_alt_horizon: `True`
  - {'test': 'leave_top5_symbols', 'removed': ['BVH', 'DPM', 'GAS', 'VTO', 'SBT'], 'incr': -0.000286583687987626, 'survived': False}
  - {'test': 'neighbor_horizons_same_sign', 'n_agree': 3, 'survived': True}
  - {'test': 'reverse_feature', 'reverse': 'streak_pos_ge3', 'same_direction_effect': np.False_, 'rev_incr': 0.0004095156349926048}
  - {'test': 'drop_strongest_year', 'year': '2011', 'incr': -0.0002706657287181252, 'survived': np.True_}
  - {'test': 'parent_condition', 'parent': 'net_neg', 'parent_incr': -0.00022956726486056303, 'ratio_parent_over_child': 0.3866898501978907}

## FFB1_0010 — `streak_neg_le_m3` T3
- killed: `False` severity=`None` reason=`None`
- survived_leave_top5: `True`
- survived_alt_horizon: `True`
  - {'test': 'leave_top5_symbols', 'removed': ['BVH', 'VIC', 'HSG', 'VTO', 'GAS'], 'incr': -0.0012012888344441102, 'survived': True}
  - {'test': 'neighbor_horizons_same_sign', 'n_agree': 3, 'survived': True}
  - {'test': 'reverse_feature', 'reverse': 'streak_pos_ge3', 'same_direction_effect': np.False_, 'rev_incr': 0.0008619052468715622}
  - {'test': 'drop_strongest_year', 'year': '2011', 'incr': -0.0007077549828940618, 'survived': np.True_}
  - {'test': 'parent_condition', 'parent': 'net_neg', 'parent_incr': -0.0006873537189092333, 'ratio_parent_over_child': 0.47723465214947175}

## FFB1_0011 — `streak_neg_le_m3` T5
- killed: `False` severity=`None` reason=`None`
- survived_leave_top5: `True`
- survived_alt_horizon: `True`
  - {'test': 'leave_top5_symbols', 'removed': ['BVH', 'VIC', 'HAG', 'GAS', 'PHR'], 'incr': -0.0017729280201068138, 'survived': True}
  - {'test': 'neighbor_horizons_same_sign', 'n_agree': 3, 'survived': True}
  - {'test': 'reverse_feature', 'reverse': 'streak_pos_ge3', 'same_direction_effect': np.False_, 'rev_incr': 0.0012929314149066273}
  - {'test': 'drop_strongest_year', 'year': '2011', 'incr': -0.00195458212095499, 'survived': np.True_}
  - {'test': 'parent_condition', 'parent': 'net_neg', 'parent_incr': -0.001083276658989963, 'ratio_parent_over_child': 0.4011722389458339}

## FFB1_0012 — `streak_neg_le_m3` T10
- killed: `False` severity=`None` reason=`None`
- survived_leave_top5: `True`
- survived_alt_horizon: `True`
  - {'test': 'leave_top5_symbols', 'removed': ['BVH', 'PVD', 'BMP', 'HAG', 'DIG'], 'incr': -0.002831621356961622, 'survived': True}
  - {'test': 'neighbor_horizons_same_sign', 'n_agree': 3, 'survived': True}
  - {'test': 'reverse_feature', 'reverse': 'streak_pos_ge3', 'same_direction_effect': np.False_, 'rev_incr': 0.0006262330998189215}
  - {'test': 'drop_strongest_year', 'year': '2011', 'incr': -0.0027193273126359563, 'survived': np.True_}
  - {'test': 'parent_condition', 'parent': 'net_neg', 'parent_incr': -0.0016533697488451907, 'ratio_parent_over_child': 0.36808173421092805}

## FFB1_0013 — `streak_pos_ge5` T1
- killed: `False` severity=`None` reason=`None`
- survived_leave_top5: `True`
- survived_alt_horizon: `True`
  - {'test': 'leave_top5_symbols', 'removed': ['BVH', 'MSN', 'GAS', 'KBC', 'HPG'], 'incr': 0.0003841893489919797, 'survived': True}
  - {'test': 'neighbor_horizons_same_sign', 'n_agree': 3, 'survived': True}
  - {'test': 'drop_strongest_year', 'year': '2013', 'incr': 0.0004498418481575791, 'survived': np.True_}
  - {'test': 'parent_condition', 'parent': 'net_pos', 'parent_incr': 0.0002896107233787365, 'ratio_parent_over_child': 0.42459145626210765}

## FFB1_0014 — `streak_pos_ge5` T3
- killed: `False` severity=`None` reason=`None`
- survived_leave_top5: `True`
- survived_alt_horizon: `True`
  - {'test': 'leave_top5_symbols', 'removed': ['BVH', 'GAS', 'KBC', 'DPM', 'HPG'], 'incr': 0.0009863771182987212, 'survived': True}
  - {'test': 'neighbor_horizons_same_sign', 'n_agree': 3, 'survived': True}
  - {'test': 'drop_strongest_year', 'year': '2009', 'incr': 0.0008470316923140047, 'survived': np.True_}
  - {'test': 'parent_condition', 'parent': 'net_pos', 'parent_incr': 0.0003422908375673555, 'ratio_parent_over_child': 0.22232302518515795}

## FFB1_0015 — `streak_pos_ge5` T5
- killed: `False` severity=`None` reason=`None`
- survived_leave_top5: `True`
- survived_alt_horizon: `True`
  - {'test': 'leave_top5_symbols', 'removed': ['BVH', 'KBC', 'GAS', 'DPM', 'HPG'], 'incr': 0.0011796982337993584, 'survived': True}
  - {'test': 'neighbor_horizons_same_sign', 'n_agree': 2, 'survived': True}
  - {'test': 'drop_strongest_year', 'year': '2009', 'incr': 0.0004947923720810385, 'survived': np.True_}
  - {'test': 'parent_condition', 'parent': 'net_pos', 'parent_incr': 0.0004943137964284101, 'ratio_parent_over_child': 0.28911046316731315}

## FFB1_0016 — `streak_neg_le_m5` T1
- killed: `False` severity=`None` reason=`None`
- survived_leave_top5: `False`
- survived_alt_horizon: `True`
  - {'test': 'leave_top5_symbols', 'removed': ['BVH', 'HAG', 'DPM', 'PVD', 'PHR'], 'incr': -0.00013150388742973936, 'survived': False}
  - {'test': 'neighbor_horizons_same_sign', 'n_agree': 3, 'survived': True}
  - {'test': 'drop_strongest_year', 'year': '2009', 'incr': -0.0006573204420884148, 'survived': np.True_}
  - {'test': 'parent_condition', 'parent': 'net_neg', 'parent_incr': -0.00022956726486056303, 'ratio_parent_over_child': 0.27693132028802664}

## FFB1_0017 — `streak_neg_le_m5` T3
- killed: `False` severity=`None` reason=`None`
- survived_leave_top5: `True`
- survived_alt_horizon: `True`
  - {'test': 'leave_top5_symbols', 'removed': ['BVH', 'HAG', 'HPG', 'PHR', 'GMD'], 'incr': -0.0017618945586512181, 'survived': True}
  - {'test': 'neighbor_horizons_same_sign', 'n_agree': 3, 'survived': True}
  - {'test': 'drop_strongest_year', 'year': '2016', 'incr': -0.002031448843788203, 'survived': np.True_}
  - {'test': 'parent_condition', 'parent': 'net_neg', 'parent_incr': -0.0006873537189092333, 'ratio_parent_over_child': 0.29403999403938025}

## FFB1_0018 — `streak_neg_le_m5` T5
- killed: `False` severity=`None` reason=`None`
- survived_leave_top5: `True`
- survived_alt_horizon: `True`
  - {'test': 'leave_top5_symbols', 'removed': ['HAG', 'BVH', 'CII', 'PVD', 'GMD'], 'incr': -0.002643738597225583, 'survived': True}
  - {'test': 'neighbor_horizons_same_sign', 'n_agree': 3, 'survived': True}
  - {'test': 'drop_strongest_year', 'year': '2016', 'incr': -0.0025678246387518273, 'survived': np.True_}
  - {'test': 'parent_condition', 'parent': 'net_neg', 'parent_incr': -0.001083276658989963, 'ratio_parent_over_child': 0.3199295056122396}

## FFB1_0019 — `streak_neg_le_m5` T10
- killed: `False` severity=`None` reason=`None`
- survived_leave_top5: `True`
- survived_alt_horizon: `True`
  - {'test': 'leave_top5_symbols', 'removed': ['BVH', 'HAG', 'PVD', 'GMD', 'BMP'], 'incr': -0.00344431464234538, 'survived': True}
  - {'test': 'neighbor_horizons_same_sign', 'n_agree': 3, 'survived': True}
  - {'test': 'drop_strongest_year', 'year': '2009', 'incr': -0.007309079272968763, 'survived': np.True_}
  - {'test': 'parent_condition', 'parent': 'net_neg', 'parent_incr': -0.0016533697488451907, 'ratio_parent_over_child': 0.35827742935116685}

## FFB1_0020 — `net_sum_5_pos` T10
- killed: `True` severity=`soft` reason=`simpler_parent_explains`
- survived_leave_top5: `False`
- survived_alt_horizon: `False`
  - {'test': 'leave_top5_symbols', 'removed': ['BVH', 'GAS', 'VOS', 'PTB', 'BMP'], 'incr': -0.0002570426793996269, 'survived': np.False_}
  - {'test': 'neighbor_horizons_same_sign', 'n_agree': 0, 'survived': False}
  - {'test': 'reverse_feature', 'reverse': 'net_sum_5_neg', 'same_direction_effect': np.False_, 'rev_incr': -0.0007946801267027215}
  - {'test': 'drop_strongest_year', 'year': '2009', 'incr': -0.0018863512685209458, 'survived': np.False_}
  - {'test': 'parent_condition', 'parent': 'net_pos', 'parent_incr': 0.0006787339959780242, 'ratio_parent_over_child': 1.124614038629379}

## FFB1_0021 — `net_sum_5_neg` T5
- killed: `True` severity=`soft` reason=`simpler_parent_explains`
- survived_leave_top5: `True`
- survived_alt_horizon: `True`
  - {'test': 'leave_top5_symbols', 'removed': ['HSG', 'HHS', 'BVH', 'PVT', 'BMP'], 'incr': -0.0006700591342820115, 'survived': True}
  - {'test': 'neighbor_horizons_same_sign', 'n_agree': 2, 'survived': True}
  - {'test': 'reverse_feature', 'reverse': 'net_sum_5_pos', 'same_direction_effect': np.False_, 'rev_incr': 0.0002976888354453396}
  - {'test': 'drop_strongest_year', 'year': '2011', 'incr': 0.0007438349630798794, 'survived': np.False_}
  - {'test': 'parent_condition', 'parent': 'net_neg', 'parent_incr': -0.001083276658989963, 'ratio_parent_over_child': 2.083063118025637}

## FFB1_0022 — `net_sum_5_neg` T10
- killed: `True` severity=`soft` reason=`simpler_parent_explains`
- survived_leave_top5: `True`
- survived_alt_horizon: `True`
  - {'test': 'leave_top5_symbols', 'removed': ['HSG', 'HHS', 'BMP', 'DIG', 'BVH'], 'incr': -0.0005037071859808338, 'survived': True}
  - {'test': 'neighbor_horizons_same_sign', 'n_agree': 3, 'survived': True}
  - {'test': 'reverse_feature', 'reverse': 'net_sum_5_pos', 'same_direction_effect': np.False_, 'rev_incr': 0.0006035261633450973}
  - {'test': 'drop_strongest_year', 'year': '2011', 'incr': 0.0017315706146838487, 'survived': np.False_}
  - {'test': 'parent_condition', 'parent': 'net_neg', 'parent_incr': -0.0016533697488451907, 'ratio_parent_over_child': 2.0805474974004134}

## FFB1_0023 — `net_sum_20_pos` T5
- killed: `True` severity=`soft` reason=`depends_on_year_2009`
- survived_leave_top5: `False`
- survived_alt_horizon: `True`
  - {'test': 'leave_top5_symbols', 'removed': ['BVH', 'TCM', 'VOS', 'PTB', 'GAS'], 'incr': 0.00013721140456080623, 'survived': False}
  - {'test': 'neighbor_horizons_same_sign', 'n_agree': 1, 'survived': True}
  - {'test': 'reverse_feature', 'reverse': 'net_sum_20_neg', 'same_direction_effect': np.False_, 'rev_incr': -0.0007029640598726711}
  - {'test': 'drop_strongest_year', 'year': '2009', 'incr': -0.0007579599471843424, 'survived': np.False_}
  - {'test': 'parent_condition', 'parent': 'net_pos', 'parent_incr': 0.0004943137964284101, 'ratio_parent_over_child': 0.8490181981017174}

## FFB1_0024 — `net_sum_20_pos` T10
- killed: `True` severity=`soft` reason=`depends_on_year_2009`
- survived_leave_top5: `False`
- survived_alt_horizon: `False`
  - {'test': 'leave_top5_symbols', 'removed': ['TCM', 'BVH', 'VOS', 'PTB', 'HSG'], 'incr': 0.0005513475910163444, 'survived': False}
  - {'test': 'neighbor_horizons_same_sign', 'n_agree': 0, 'survived': False}
  - {'test': 'reverse_feature', 'reverse': 'net_sum_20_neg', 'same_direction_effect': np.False_, 'rev_incr': -0.0015724226404910417}
  - {'test': 'drop_strongest_year', 'year': '2009', 'incr': -0.0011727529636201355, 'survived': np.False_}
  - {'test': 'parent_condition', 'parent': 'net_pos', 'parent_incr': 0.0006787339959780242, 'ratio_parent_over_child': 0.48189355259134514}

## FFB1_0025 — `net_sum_20_neg` T5
- killed: `True` severity=`soft` reason=`simpler_parent_explains`
- survived_leave_top5: `True`
- survived_alt_horizon: `True`
  - {'test': 'leave_top5_symbols', 'removed': ['VHC', 'HHS', 'GIL', 'IJC', 'BMP'], 'incr': -0.0009013384513234403, 'survived': True}
  - {'test': 'neighbor_horizons_same_sign', 'n_agree': 3, 'survived': True}
  - {'test': 'reverse_feature', 'reverse': 'net_sum_20_pos', 'same_direction_effect': np.False_, 'rev_incr': 0.0005822181403574442}
  - {'test': 'drop_strongest_year', 'year': '2011', 'incr': 0.0007884035912544502, 'survived': np.False_}
  - {'test': 'parent_condition', 'parent': 'net_neg', 'parent_incr': -0.001083276658989963, 'ratio_parent_over_child': 1.5410128637105267}

## FFB1_0026 — `net_sum_20_neg` T10
- killed: `True` severity=`soft` reason=`simpler_parent_explains`
- survived_leave_top5: `True`
- survived_alt_horizon: `True`
  - {'test': 'leave_top5_symbols', 'removed': ['VHC', 'HHS', 'BMP', 'IJC', 'HAG'], 'incr': -0.0012666309109278981, 'survived': True}
  - {'test': 'neighbor_horizons_same_sign', 'n_agree': 3, 'survived': True}
  - {'test': 'reverse_feature', 'reverse': 'net_sum_20_pos', 'same_direction_effect': np.False_, 'rev_incr': 0.0014084728719199184}
  - {'test': 'drop_strongest_year', 'year': '2011', 'incr': 0.0014355637153109955, 'survived': np.False_}
  - {'test': 'parent_condition', 'parent': 'net_neg', 'parent_incr': -0.0016533697488451907, 'ratio_parent_over_child': 1.0514792310093364}

## FFB1_0027 — `abn_net_pos_z15` T1
- killed: `True` severity=`soft` reason=`reverse_feature_same_direction`
- survived_leave_top5: `True`
- survived_alt_horizon: `True`
  - {'test': 'leave_top5_symbols', 'removed': ['VHC', 'MSN', 'DIG', 'BVH', 'GAS'], 'incr': 0.0015239548383124129, 'survived': True}
  - {'test': 'neighbor_horizons_same_sign', 'n_agree': 3, 'survived': True}
  - {'test': 'reverse_feature', 'reverse': 'abn_net_neg_z15', 'same_direction_effect': True, 'rev_incr': 0.00138659723136382}
  - {'test': 'drop_strongest_year', 'year': '2009', 'incr': 0.0015782836433752931, 'survived': np.True_}
  - {'test': 'parent_condition', 'parent': 'net_pos', 'parent_incr': 0.0002896107233787365, 'ratio_parent_over_child': 0.13305029481923716}

## FFB1_0028 — `abn_net_pos_z15` T3
- killed: `True` severity=`soft` reason=`reverse_feature_same_direction`
- survived_leave_top5: `True`
- survived_alt_horizon: `True`
  - {'test': 'leave_top5_symbols', 'removed': ['BVH', 'STB', 'VHC', 'KSB', 'SSI'], 'incr': 0.0018111755149138086, 'survived': True}
  - {'test': 'neighbor_horizons_same_sign', 'n_agree': 3, 'survived': True}
  - {'test': 'reverse_feature', 'reverse': 'abn_net_neg_z15', 'same_direction_effect': True, 'rev_incr': 0.0013221723984660908}
  - {'test': 'drop_strongest_year', 'year': '2009', 'incr': 0.001393123055894154, 'survived': np.True_}
  - {'test': 'parent_condition', 'parent': 'net_pos', 'parent_incr': 0.0003422908375673555, 'ratio_parent_over_child': 0.1305972004778983}

## FFB1_0029 — `abn_net_pos_z15` T5
- killed: `False` severity=`None` reason=`None`
- survived_leave_top5: `True`
- survived_alt_horizon: `True`
  - {'test': 'leave_top5_symbols', 'removed': ['BVH', 'BMP', 'STB', 'CII', 'VHC'], 'incr': 0.0023452154474948358, 'survived': True}
  - {'test': 'neighbor_horizons_same_sign', 'n_agree': 3, 'survived': True}
  - {'test': 'reverse_feature', 'reverse': 'abn_net_neg_z15', 'same_direction_effect': False, 'rev_incr': 0.0003428355467431654}
  - {'test': 'drop_strongest_year', 'year': '2009', 'incr': 0.0003911605982085532, 'survived': np.True_}
  - {'test': 'parent_condition', 'parent': 'net_pos', 'parent_incr': 0.0004943137964284101, 'ratio_parent_over_child': 0.1740402813600219}

## FFB1_0030 — `abn_net_pos_z15` T10
- killed: `False` severity=`None` reason=`None`
- survived_leave_top5: `True`
- survived_alt_horizon: `True`
  - {'test': 'leave_top5_symbols', 'removed': ['BVH', 'BMP', 'CII', 'DIG', 'GAS'], 'incr': 0.00355617617295575, 'survived': True}
  - {'test': 'neighbor_horizons_same_sign', 'n_agree': 3, 'survived': True}
  - {'test': 'reverse_feature', 'reverse': 'abn_net_neg_z15', 'same_direction_effect': False, 'rev_incr': 0.0009321834950229005}
  - {'test': 'drop_strongest_year', 'year': '2009', 'incr': 0.002227916166940673, 'survived': np.True_}
  - {'test': 'parent_condition', 'parent': 'net_pos', 'parent_incr': 0.0006787339959780242, 'ratio_parent_over_child': 0.12353455996417374}

## FFB1_0031 — `abn_net_neg_z15` T1
- killed: `True` severity=`soft` reason=`reverse_feature_same_direction`
- survived_leave_top5: `False`
- survived_alt_horizon: `True`
  - {'test': 'leave_top5_symbols', 'removed': ['GIL', 'STB', 'KBC', 'CMG', 'BMP'], 'incr': 0.0006561900053237871, 'survived': False}
  - {'test': 'neighbor_horizons_same_sign', 'n_agree': 3, 'survived': True}
  - {'test': 'reverse_feature', 'reverse': 'abn_net_pos_z15', 'same_direction_effect': True, 'rev_incr': 0.002176701102182473}
  - {'test': 'drop_strongest_year', 'year': '2009', 'incr': 0.0009326890485252788, 'survived': np.True_}
  - {'test': 'parent_condition', 'parent': 'net_neg', 'parent_incr': -0.00022956726486056303, 'ratio_parent_over_child': 0.16556160626021646}

## FFB1_0032 — `abn_net_neg_z15` T3
- killed: `True` severity=`soft` reason=`reverse_feature_same_direction`
- survived_leave_top5: `True`
- survived_alt_horizon: `True`
  - {'test': 'leave_top5_symbols', 'removed': ['REE', 'STB', 'BMP', 'HDC', 'NTL'], 'incr': 0.0006908602981232907, 'survived': True}
  - {'test': 'neighbor_horizons_same_sign', 'n_agree': 3, 'survived': True}
  - {'test': 'reverse_feature', 'reverse': 'abn_net_pos_z15', 'same_direction_effect': True, 'rev_incr': 0.0026209661180699147}
  - {'test': 'drop_strongest_year', 'year': '2009', 'incr': 0.00025654317228044016, 'survived': np.True_}
  - {'test': 'parent_condition', 'parent': 'net_neg', 'parent_incr': -0.0006873537189092333, 'ratio_parent_over_child': 0.5198669399744406}

## FFB1_0033 — `abn_net_neg_z15` T10
- killed: `True` severity=`soft` reason=`depends_on_year_2009`
- survived_leave_top5: `False`
- survived_alt_horizon: `True`
  - {'test': 'leave_top5_symbols', 'removed': ['BMP', 'HDC', 'REE', 'KBC', 'STB'], 'incr': -0.0010068013930848918, 'survived': np.False_}
  - {'test': 'neighbor_horizons_same_sign', 'n_agree': 1, 'survived': True}
  - {'test': 'reverse_feature', 'reverse': 'abn_net_pos_z15', 'same_direction_effect': True, 'rev_incr': 0.005494284321528031}
  - {'test': 'drop_strongest_year', 'year': '2009', 'incr': -0.002118597537794639, 'survived': np.False_}
  - {'test': 'parent_condition', 'parent': 'net_neg', 'parent_incr': -0.0016533697488451907, 'ratio_parent_over_child': 1.7736526742565561}

## FFB1_0034 — `abn_net_pos_z20` T1
- killed: `True` severity=`soft` reason=`reverse_feature_same_direction`
- survived_leave_top5: `True`
- survived_alt_horizon: `True`
  - {'test': 'leave_top5_symbols', 'removed': ['VHC', 'KSB', 'MSN', 'CTG', 'DIG'], 'incr': 0.0015693680745249568, 'survived': True}
  - {'test': 'neighbor_horizons_same_sign', 'n_agree': 3, 'survived': True}
  - {'test': 'reverse_feature', 'reverse': 'abn_net_neg_z20', 'same_direction_effect': True, 'rev_incr': 0.0022763123538122095}
  - {'test': 'drop_strongest_year', 'year': '2009', 'incr': 0.0016360860283779618, 'survived': np.True_}
  - {'test': 'parent_condition', 'parent': 'net_pos', 'parent_incr': 0.0002896107233787365, 'ratio_parent_over_child': 0.12597293450140132}

## FFB1_0035 — `abn_net_pos_z20` T3
- killed: `True` severity=`soft` reason=`reverse_feature_same_direction`
- survived_leave_top5: `True`
- survived_alt_horizon: `True`
  - {'test': 'leave_top5_symbols', 'removed': ['BVH', 'STB', 'KSB', 'VHC', 'VOS'], 'incr': 0.002090384848983859, 'survived': True}
  - {'test': 'neighbor_horizons_same_sign', 'n_agree': 3, 'survived': True}
  - {'test': 'reverse_feature', 'reverse': 'abn_net_neg_z20', 'same_direction_effect': True, 'rev_incr': 0.001971972644977341}
  - {'test': 'drop_strongest_year', 'year': '2009', 'incr': 0.0012617448904889612, 'survived': np.True_}
  - {'test': 'parent_condition', 'parent': 'net_pos', 'parent_incr': 0.0003422908375673555, 'ratio_parent_over_child': 0.1430070458171294}

## FFB1_0036 — `abn_net_pos_z20` T5
- killed: `True` severity=`soft` reason=`depends_on_year_2009`
- survived_leave_top5: `True`
- survived_alt_horizon: `True`
  - {'test': 'leave_top5_symbols', 'removed': ['BVH', 'STB', 'DPR', 'BMP', 'VHC'], 'incr': 0.0009571550428005538, 'survived': True}
  - {'test': 'neighbor_horizons_same_sign', 'n_agree': 3, 'survived': True}
  - {'test': 'reverse_feature', 'reverse': 'abn_net_neg_z20', 'same_direction_effect': True, 'rev_incr': 0.0009919620880365458}
  - {'test': 'drop_strongest_year', 'year': '2009', 'incr': -0.00011401372182335548, 'survived': np.False_}
  - {'test': 'parent_condition', 'parent': 'net_pos', 'parent_incr': 0.0004943137964284101, 'ratio_parent_over_child': 0.267177697337577}

## FFB1_0037 — `abn_net_pos_z20` T10
- killed: `False` severity=`None` reason=`None`
- survived_leave_top5: `True`
- survived_alt_horizon: `True`
  - {'test': 'leave_top5_symbols', 'removed': ['BVH', 'BMP', 'KBC', 'CII', 'HDC'], 'incr': 0.004751081247578043, 'survived': True}
  - {'test': 'neighbor_horizons_same_sign', 'n_agree': 3, 'survived': True}
  - {'test': 'reverse_feature', 'reverse': 'abn_net_neg_z20', 'same_direction_effect': False, 'rev_incr': 0.0012068963793874516}
  - {'test': 'drop_strongest_year', 'year': '2009', 'incr': 0.002461153322252662, 'survived': np.True_}
  - {'test': 'parent_condition', 'parent': 'net_pos', 'parent_incr': 0.0006787339959780242, 'ratio_parent_over_child': 0.13440299073770545}

## FFB1_0038 — `abn_net_neg_z20` T1
- killed: `True` severity=`soft` reason=`reverse_feature_same_direction`
- survived_leave_top5: `True`
- survived_alt_horizon: `True`
  - {'test': 'leave_top5_symbols', 'removed': ['STB', 'GIL', 'CMG', 'AGR', 'KBC'], 'incr': 0.0018246871338173697, 'survived': True}
  - {'test': 'neighbor_horizons_same_sign', 'n_agree': 3, 'survived': True}
  - {'test': 'reverse_feature', 'reverse': 'abn_net_pos_z20', 'same_direction_effect': True, 'rev_incr': 0.0022989916407441862}
  - {'test': 'drop_strongest_year', 'year': '2016', 'incr': 0.002015709728823703, 'survived': np.True_}
  - {'test': 'parent_condition', 'parent': 'net_neg', 'parent_incr': -0.00022956726486056303, 'ratio_parent_over_child': 0.10085051134397252}

## FFB1_0039 — `abn_net_neg_z20` T3
- killed: `True` severity=`soft` reason=`reverse_feature_same_direction`
- survived_leave_top5: `True`
- survived_alt_horizon: `True`
  - {'test': 'leave_top5_symbols', 'removed': ['REE', 'STB', 'BMP', 'IJC', 'HDC'], 'incr': 0.001513180285186811, 'survived': True}
  - {'test': 'neighbor_horizons_same_sign', 'n_agree': 3, 'survived': True}
  - {'test': 'reverse_feature', 'reverse': 'abn_net_pos_z20', 'same_direction_effect': True, 'rev_incr': 0.0023935242883421333}
  - {'test': 'drop_strongest_year', 'year': '2012', 'incr': 0.0009942766816246188, 'survived': np.True_}
  - {'test': 'parent_condition', 'parent': 'net_neg', 'parent_incr': -0.0006873537189092333, 'ratio_parent_over_child': 0.348561487736627}

## FFB1_0040 — `abn_net_neg_z20` T5
- killed: `True` severity=`soft` reason=`depends_on_year_2012`
- survived_leave_top5: `False`
- survived_alt_horizon: `True`
  - {'test': 'leave_top5_symbols', 'removed': ['REE', 'STB', 'HDC', 'HPG', 'BMP'], 'incr': -0.0001416720741281546, 'survived': np.False_}
  - {'test': 'neighbor_horizons_same_sign', 'n_agree': 3, 'survived': True}
  - {'test': 'reverse_feature', 'reverse': 'abn_net_pos_z20', 'same_direction_effect': True, 'rev_incr': 0.0018501312098810716}
  - {'test': 'drop_strongest_year', 'year': '2012', 'incr': -0.0002080782062503896, 'survived': np.False_}
  - {'test': 'parent_condition', 'parent': 'net_neg', 'parent_incr': -0.001083276658989963, 'ratio_parent_over_child': 1.0920544968953017}

## FFB1_0041 — `abn_net_neg_z20` T10
- killed: `True` severity=`soft` reason=`depends_on_year_2009`
- survived_leave_top5: `True`
- survived_alt_horizon: `True`
  - {'test': 'leave_top5_symbols', 'removed': ['REE', 'STB', 'BMP', 'HDC', 'VCB'], 'incr': 0.0010091012664980136, 'survived': True}
  - {'test': 'neighbor_horizons_same_sign', 'n_agree': 3, 'survived': True}
  - {'test': 'reverse_feature', 'reverse': 'abn_net_pos_z20', 'same_direction_effect': True, 'rev_incr': 0.005049991761735492}
  - {'test': 'drop_strongest_year', 'year': '2009', 'incr': -0.001621604422527848, 'survived': np.False_}
  - {'test': 'parent_condition', 'parent': 'net_neg', 'parent_incr': -0.0016533697488451907, 'ratio_parent_over_child': 1.3699351303749392}

## FFB1_0042 — `abn_abs_z20` T1
- killed: `False` severity=`None` reason=`None`
- survived_leave_top5: `True`
- survived_alt_horizon: `True`
  - {'test': 'leave_top5_symbols', 'removed': ['VHC', 'PVT', 'KBC', 'MSN', 'CTG'], 'incr': 0.0017409932810735975, 'survived': True}
  - {'test': 'neighbor_horizons_same_sign', 'n_agree': 3, 'survived': True}
  - {'test': 'drop_strongest_year', 'year': '2009', 'incr': 0.0017681042432085132, 'survived': np.True_}

## FFB1_0043 — `abn_abs_z20` T3
- killed: `False` severity=`None` reason=`None`
- survived_leave_top5: `True`
- survived_alt_horizon: `True`
  - {'test': 'leave_top5_symbols', 'removed': ['VHC', 'REE', 'CTG', 'IJC', 'BMP'], 'incr': 0.0016999923247481303, 'survived': True}
  - {'test': 'neighbor_horizons_same_sign', 'n_agree': 3, 'survived': True}
  - {'test': 'drop_strongest_year', 'year': '2009', 'incr': 0.0011882394861023504, 'survived': np.True_}

## FFB1_0044 — `abn_abs_z20` T5
- killed: `True` severity=`soft` reason=`depends_on_year_2009`
- survived_leave_top5: `True`
- survived_alt_horizon: `True`
  - {'test': 'leave_top5_symbols', 'removed': ['BMP', 'HDC', 'VHC', 'REE', 'HCM'], 'incr': 0.0011426494834987004, 'survived': True}
  - {'test': 'neighbor_horizons_same_sign', 'n_agree': 3, 'survived': True}
  - {'test': 'drop_strongest_year', 'year': '2009', 'incr': -0.00013966051960070133, 'survived': np.False_}

## FFB1_0045 — `abn_abs_z20` T10
- killed: `False` severity=`None` reason=`None`
- survived_leave_top5: `True`
- survived_alt_horizon: `True`
  - {'test': 'leave_top5_symbols', 'removed': ['BMP', 'HDC', 'REE', 'IJC', 'VPL'], 'incr': 0.001692008379619904, 'survived': True}
  - {'test': 'neighbor_horizons_same_sign', 'n_agree': 3, 'survived': True}
  - {'test': 'drop_strongest_year', 'year': '2009', 'incr': 0.00046960100517962565, 'survived': np.True_}

## FFB1_0046 — `net_hi_pct90` T1
- killed: `True` severity=`soft` reason=`reverse_feature_same_direction`
- survived_leave_top5: `True`
- survived_alt_horizon: `True`
  - {'test': 'leave_top5_symbols', 'removed': ['NKG', 'DIG', 'VSC', 'BVH', 'HSG'], 'incr': 0.0003423273324165161, 'survived': True}
  - {'test': 'neighbor_horizons_same_sign', 'n_agree': 3, 'survived': True}
  - {'test': 'reverse_feature', 'reverse': 'net_lo_pct10', 'same_direction_effect': True, 'rev_incr': 0.0005679926333548815}
  - {'test': 'drop_strongest_year', 'year': '2013', 'incr': 0.00036188676063059373, 'survived': np.True_}

## FFB1_0047 — `net_hi_pct90` T5
- killed: `True` severity=`soft` reason=`depends_on_year_2014`
- survived_leave_top5: `False`
- survived_alt_horizon: `True`
  - {'test': 'leave_top5_symbols', 'removed': ['VSC', 'NKG', 'HDG', 'BVH', 'IJC'], 'incr': -0.0004782327446047389, 'survived': np.False_}
  - {'test': 'neighbor_horizons_same_sign', 'n_agree': 1, 'survived': True}
  - {'test': 'reverse_feature', 'reverse': 'net_lo_pct10', 'same_direction_effect': np.False_, 'rev_incr': -0.0015096994931921245}
  - {'test': 'drop_strongest_year', 'year': '2014', 'incr': -0.00031402149008215796, 'survived': np.False_}

## FFB1_0048 — `net_hi_pct90` T10
- killed: `False` severity=`None` reason=`None`
- survived_leave_top5: `False`
- survived_alt_horizon: `False`
  - {'test': 'leave_top5_symbols', 'removed': ['NKG', 'VSC', 'HCM', 'BVH', 'KSB'], 'incr': 0.0008897378386388945, 'survived': False}
  - {'test': 'neighbor_horizons_same_sign', 'n_agree': 0, 'survived': False}
  - {'test': 'reverse_feature', 'reverse': 'net_lo_pct10', 'same_direction_effect': np.False_, 'rev_incr': -0.0036769519109387926}
  - {'test': 'drop_strongest_year', 'year': '2013', 'incr': 0.00045867346048966196, 'survived': np.True_}

## FFB1_0049 — `net_lo_pct10` T1
- killed: `True` severity=`soft` reason=`reverse_feature_same_direction`
- survived_leave_top5: `True`
- survived_alt_horizon: `False`
  - {'test': 'leave_top5_symbols', 'removed': ['REE', 'CMG', 'KBC', 'VHC', 'BMP'], 'incr': 0.00037291251478814883, 'survived': True}
  - {'test': 'neighbor_horizons_same_sign', 'n_agree': 0, 'survived': False}
  - {'test': 'reverse_feature', 'reverse': 'net_hi_pct90', 'same_direction_effect': True, 'rev_incr': 0.0005458876532636595}
  - {'test': 'drop_strongest_year', 'year': '2011', 'incr': 0.0011211731076200444, 'survived': np.True_}

## FFB1_0050 — `net_lo_pct10` T5
- killed: `True` severity=`soft` reason=`depends_on_year_2011`
- survived_leave_top5: `False`
- survived_alt_horizon: `True`
  - {'test': 'leave_top5_symbols', 'removed': ['BVH', 'REE', 'HHS', 'IJC', 'HPG'], 'incr': -0.0003600197491920279, 'survived': False}
  - {'test': 'neighbor_horizons_same_sign', 'n_agree': 3, 'survived': True}
  - {'test': 'reverse_feature', 'reverse': 'net_hi_pct90', 'same_direction_effect': np.False_, 'rev_incr': 0.0006235346561969731}
  - {'test': 'drop_strongest_year', 'year': '2011', 'incr': 2.8217337033649773e-05, 'survived': np.False_}

## FFB1_0051 — `net_lo_pct10` T10
- killed: `False` severity=`None` reason=`None`
- survived_leave_top5: `True`
- survived_alt_horizon: `True`
  - {'test': 'leave_top5_symbols', 'removed': ['REE', 'HHS', 'BVH', 'PTB', 'VCB'], 'incr': -0.0020903967537486546, 'survived': True}
  - {'test': 'neighbor_horizons_same_sign', 'n_agree': 3, 'survived': True}
  - {'test': 'reverse_feature', 'reverse': 'net_hi_pct90', 'same_direction_effect': np.False_, 'rev_incr': 0.002070706147217414}
  - {'test': 'drop_strongest_year', 'year': '2011', 'incr': -0.0008673856668804385, 'survived': np.True_}

## FFB1_0052 — `trans_pos_to_neg` T3
- killed: `False` severity=`None` reason=`None`
- survived_leave_top5: `True`
- survived_alt_horizon: `True`
  - {'test': 'leave_top5_symbols', 'removed': ['BMP', 'SBT', 'HAG', 'PET', 'SSI'], 'incr': -0.0009331402950468469, 'survived': True}
  - {'test': 'neighbor_horizons_same_sign', 'n_agree': 2, 'survived': True}
  - {'test': 'reverse_feature', 'reverse': 'trans_neg_to_pos', 'same_direction_effect': False, 'rev_incr': -0.0003965511240997232}
  - {'test': 'drop_strongest_year', 'year': '2009', 'incr': -0.0023872276920446412, 'survived': np.True_}
  - {'test': 'parent_condition', 'parent': 'net_neg', 'parent_incr': -0.0006873537189092333, 'ratio_parent_over_child': 0.7009554271554677}

## FFB1_0053 — `trans_pos_to_neg` T5
- killed: `True` severity=`soft` reason=`simpler_parent_explains`
- survived_leave_top5: `True`
- survived_alt_horizon: `True`
  - {'test': 'leave_top5_symbols', 'removed': ['HAG', 'PET', 'BMP', 'HSG', 'SBT'], 'incr': -0.000868344927500713, 'survived': True}
  - {'test': 'neighbor_horizons_same_sign', 'n_agree': 3, 'survived': True}
  - {'test': 'reverse_feature', 'reverse': 'trans_neg_to_pos', 'same_direction_effect': True, 'rev_incr': -0.0007769373867731874}
  - {'test': 'drop_strongest_year', 'year': '2009', 'incr': -0.0027485167595760725, 'survived': np.True_}
  - {'test': 'parent_condition', 'parent': 'net_neg', 'parent_incr': -0.001083276658989963, 'ratio_parent_over_child': 1.3801314166224354}

## FFB1_0054 — `trans_pos_to_neg` T10
- killed: `True` severity=`soft` reason=`simpler_parent_explains`
- survived_leave_top5: `True`
- survived_alt_horizon: `True`
  - {'test': 'leave_top5_symbols', 'removed': ['HSG', 'HAG', 'HHS', 'BMP', 'KBC'], 'incr': -0.0013422688289234936, 'survived': True}
  - {'test': 'neighbor_horizons_same_sign', 'n_agree': 3, 'survived': True}
  - {'test': 'reverse_feature', 'reverse': 'trans_neg_to_pos', 'same_direction_effect': np.False_, 'rev_incr': 0.00044778747365014}
  - {'test': 'drop_strongest_year', 'year': '2009', 'incr': -0.004287195664213989, 'survived': np.True_}
  - {'test': 'parent_condition', 'parent': 'net_neg', 'parent_incr': -0.0016533697488451907, 'ratio_parent_over_child': 1.5763296668916609}

## FFB1_0055 — `trans_neg_to_pos` T5
- killed: `True` severity=`soft` reason=`reverse_feature_same_direction`
- survived_leave_top5: `True`
- survived_alt_horizon: `True`
  - {'test': 'leave_top5_symbols', 'removed': ['VNM', 'HAG', 'CII', 'HHS', 'PET'], 'incr': -0.0006111549834887508, 'survived': True}
  - {'test': 'neighbor_horizons_same_sign', 'n_agree': 2, 'survived': True}
  - {'test': 'reverse_feature', 'reverse': 'trans_pos_to_neg', 'same_direction_effect': True, 'rev_incr': -0.000784908339845666}
  - {'test': 'drop_strongest_year', 'year': '2009', 'incr': -0.0023287441723114973, 'survived': np.True_}
  - {'test': 'parent_condition', 'parent': 'net_pos', 'parent_incr': 0.0004943137964284101, 'ratio_parent_over_child': 0.6362337620041909}

## FFB1_0056 — `agree_pos` T1
- killed: `False` severity=`None` reason=`None`
- survived_leave_top5: `True`
- survived_alt_horizon: `True`
  - {'test': 'leave_top5_symbols', 'removed': ['BVH', 'HSG', 'HPG', 'SSI', 'MSN'], 'incr': 0.001890196749857216, 'survived': True}
  - {'test': 'neighbor_horizons_same_sign', 'n_agree': 3, 'survived': True}
  - {'test': 'reverse_feature', 'reverse': 'agree_neg', 'same_direction_effect': np.False_, 'rev_incr': -0.0019350969245028893}
  - {'test': 'drop_strongest_year', 'year': '2009', 'incr': 0.0014021207252672132, 'survived': np.True_}
  - {'test': 'parent_condition', 'parent': 'net_pos', 'parent_incr': 0.0002896107233787365, 'ratio_parent_over_child': 0.1282110530711328}

## FFB1_0057 — `agree_pos` T3
- killed: `False` severity=`None` reason=`None`
- survived_leave_top5: `True`
- survived_alt_horizon: `True`
  - {'test': 'leave_top5_symbols', 'removed': ['BVH', 'SSI', 'MSN', 'HSG', 'HPG'], 'incr': 0.00133317553063882, 'survived': True}
  - {'test': 'neighbor_horizons_same_sign', 'n_agree': 3, 'survived': True}
  - {'test': 'reverse_feature', 'reverse': 'agree_neg', 'same_direction_effect': np.False_, 'rev_incr': -0.0028756236006988126}
  - {'test': 'drop_strongest_year', 'year': '2009', 'incr': 0.0007148292970218351, 'survived': np.True_}
  - {'test': 'parent_condition', 'parent': 'net_pos', 'parent_incr': 0.0003422908375673555, 'ratio_parent_over_child': 0.17164406482848796}

## FFB1_0058 — `agree_pos` T5
- killed: `False` severity=`None` reason=`None`
- survived_leave_top5: `True`
- survived_alt_horizon: `True`
  - {'test': 'leave_top5_symbols', 'removed': ['BVH', 'HSG', 'SSI', 'MSN', 'HPG'], 'incr': 0.0018858416876923426, 'survived': True}
  - {'test': 'neighbor_horizons_same_sign', 'n_agree': 3, 'survived': True}
  - {'test': 'reverse_feature', 'reverse': 'agree_neg', 'same_direction_effect': np.False_, 'rev_incr': -0.0035892167637805415}
  - {'test': 'drop_strongest_year', 'year': '2009', 'incr': 0.0006533259917886718, 'survived': np.True_}
  - {'test': 'parent_condition', 'parent': 'net_pos', 'parent_incr': 0.0004943137964284101, 'ratio_parent_over_child': 0.17007289209402848}

## FFB1_0059 — `agree_pos` T10
- killed: `False` severity=`None` reason=`None`
- survived_leave_top5: `True`
- survived_alt_horizon: `True`
  - {'test': 'leave_top5_symbols', 'removed': ['BVH', 'HSG', 'SSI', 'GAS', 'HPG'], 'incr': 0.0018148543734983118, 'survived': True}
  - {'test': 'neighbor_horizons_same_sign', 'n_agree': 3, 'survived': True}
  - {'test': 'reverse_feature', 'reverse': 'agree_neg', 'same_direction_effect': np.False_, 'rev_incr': -0.0043812038927696535}
  - {'test': 'drop_strongest_year', 'year': '2009', 'incr': 0.00021847609979139412, 'survived': np.True_}
  - {'test': 'parent_condition', 'parent': 'net_pos', 'parent_incr': 0.0006787339959780242, 'ratio_parent_over_child': 0.19013011673440733}

## FFB1_0060 — `agree_neg` T1
- killed: `False` severity=`None` reason=`None`
- survived_leave_top5: `True`
- survived_alt_horizon: `True`
  - {'test': 'leave_top5_symbols', 'removed': ['VIC', 'HAG', 'BVH', 'HSG', 'DIG'], 'incr': -0.0014697907282281719, 'survived': True}
  - {'test': 'neighbor_horizons_same_sign', 'n_agree': 3, 'survived': True}
  - {'test': 'reverse_feature', 'reverse': 'agree_pos', 'same_direction_effect': np.False_, 'rev_incr': 0.0022588592515347134}
  - {'test': 'drop_strongest_year', 'year': '2011', 'incr': -0.00126889149215749, 'survived': np.True_}
  - {'test': 'parent_condition', 'parent': 'net_neg', 'parent_incr': -0.00022956726486056303, 'ratio_parent_over_child': 0.11863347099243465}

## FFB1_0061 — `agree_neg` T3
- killed: `False` severity=`None` reason=`None`
- survived_leave_top5: `True`
- survived_alt_horizon: `True`
  - {'test': 'leave_top5_symbols', 'removed': ['HAG', 'BVH', 'SSI', 'DPM', 'DIG'], 'incr': -0.0022089306179944564, 'survived': True}
  - {'test': 'neighbor_horizons_same_sign', 'n_agree': 3, 'survived': True}
  - {'test': 'reverse_feature', 'reverse': 'agree_pos', 'same_direction_effect': np.False_, 'rev_incr': 0.001994189766534503}
  - {'test': 'drop_strongest_year', 'year': '2011', 'incr': -0.0013037834377937923, 'survived': np.True_}
  - {'test': 'parent_condition', 'parent': 'net_neg', 'parent_incr': -0.0006873537189092333, 'ratio_parent_over_child': 0.23902770819595365}

## FFB1_0062 — `agree_neg` T5
- killed: `False` severity=`None` reason=`None`
- survived_leave_top5: `True`
- survived_alt_horizon: `True`
  - {'test': 'leave_top5_symbols', 'removed': ['HAG', 'BVH', 'DPM', 'GMD', 'DIG'], 'incr': -0.002639940286722848, 'survived': True}
  - {'test': 'neighbor_horizons_same_sign', 'n_agree': 3, 'survived': True}
  - {'test': 'reverse_feature', 'reverse': 'agree_pos', 'same_direction_effect': np.False_, 'rev_incr': 0.00290648198159127}
  - {'test': 'drop_strongest_year', 'year': '2011', 'incr': -0.001427921632952983, 'survived': np.True_}
  - {'test': 'parent_condition', 'parent': 'net_neg', 'parent_incr': -0.001083276658989963, 'ratio_parent_over_child': 0.3018142202837986}

## FFB1_0063 — `agree_neg` T10
- killed: `False` severity=`None` reason=`None`
- survived_leave_top5: `True`
- survived_alt_horizon: `True`
  - {'test': 'leave_top5_symbols', 'removed': ['HAG', 'BMP', 'BVH', 'DIG', 'PVD'], 'incr': -0.0035111313522041662, 'survived': True}
  - {'test': 'neighbor_horizons_same_sign', 'n_agree': 3, 'survived': True}
  - {'test': 'reverse_feature', 'reverse': 'agree_pos', 'same_direction_effect': np.False_, 'rev_incr': 0.0035698394743329765}
  - {'test': 'drop_strongest_year', 'year': '2011', 'incr': -0.0008322094067790221, 'survived': np.True_}
  - {'test': 'parent_condition', 'parent': 'net_neg', 'parent_incr': -0.0016533697488451907, 'ratio_parent_over_child': 0.37737795120052825}

## FFB1_0064 — `diverge_buy_down` T1
- killed: `False` severity=`None` reason=`None`
- survived_leave_top5: `True`
- survived_alt_horizon: `True`
  - {'test': 'leave_top5_symbols', 'removed': ['NTL', 'KBC', 'STB', 'DIG', 'HSG'], 'incr': -0.001561998889413144, 'survived': True}
  - {'test': 'neighbor_horizons_same_sign', 'n_agree': 2, 'survived': True}
  - {'test': 'reverse_feature', 'reverse': 'diverge_sell_up', 'same_direction_effect': np.False_, 'rev_incr': 0.0022410619509697642}
  - {'test': 'drop_strongest_year', 'year': '2009', 'incr': -0.001400185035639584, 'survived': np.True_}
  - {'test': 'parent_condition', 'parent': 'net_pos', 'parent_incr': 0.0002896107233787365, 'ratio_parent_over_child': 0.1610518477188563}

## FFB1_0065 — `diverge_buy_down` T3
- killed: `False` severity=`None` reason=`None`
- survived_leave_top5: `True`
- survived_alt_horizon: `True`
  - {'test': 'leave_top5_symbols', 'removed': ['BVH', 'DIG', 'STB', 'HHS', 'KBC'], 'incr': -0.001021305709798075, 'survived': True}
  - {'test': 'neighbor_horizons_same_sign', 'n_agree': 3, 'survived': True}
  - {'test': 'reverse_feature', 'reverse': 'diverge_sell_up', 'same_direction_effect': np.False_, 'rev_incr': 0.0023538537519954858}
  - {'test': 'drop_strongest_year', 'year': '2011', 'incr': -0.0004537004091134725, 'survived': np.True_}
  - {'test': 'parent_condition', 'parent': 'net_pos', 'parent_incr': 0.0003422908375673555, 'ratio_parent_over_child': 0.2531008596816046}

## FFB1_0066 — `diverge_buy_down` T5
- killed: `False` severity=`None` reason=`None`
- survived_leave_top5: `True`
- survived_alt_horizon: `True`
  - {'test': 'leave_top5_symbols', 'removed': ['HHS', 'BVH', 'GAS', 'NTL', 'KBC'], 'incr': -0.001582566783623162, 'survived': True}
  - {'test': 'neighbor_horizons_same_sign', 'n_agree': 3, 'survived': True}
  - {'test': 'reverse_feature', 'reverse': 'diverge_sell_up', 'same_direction_effect': np.False_, 'rev_incr': 0.0016306905687835458}
  - {'test': 'drop_strongest_year', 'year': '2011', 'incr': -6.390726851550007e-05, 'survived': np.True_}
  - {'test': 'parent_condition', 'parent': 'net_pos', 'parent_incr': 0.0004943137964284101, 'ratio_parent_over_child': 0.29855894860427834}

## FFB1_0067 — `diverge_buy_down` T10
- killed: `True` severity=`soft` reason=`depends_on_year_2011`
- survived_leave_top5: `True`
- survived_alt_horizon: `True`
  - {'test': 'leave_top5_symbols', 'removed': ['HHS', 'BVH', 'GAS', 'KBC', 'DIG'], 'incr': -0.0011855521561012108, 'survived': True}
  - {'test': 'neighbor_horizons_same_sign', 'n_agree': 3, 'survived': True}
  - {'test': 'reverse_feature', 'reverse': 'diverge_sell_up', 'same_direction_effect': np.False_, 'rev_incr': 0.0014081959204589295}
  - {'test': 'drop_strongest_year', 'year': '2011', 'incr': 0.0012845186437316386, 'survived': np.False_}
  - {'test': 'parent_condition', 'parent': 'net_pos', 'parent_incr': 0.0006787339959780242, 'ratio_parent_over_child': 0.42238539296911526}

## FFB1_0068 — `diverge_sell_up` T1
- killed: `False` severity=`None` reason=`None`
- survived_leave_top5: `True`
- survived_alt_horizon: `True`
  - {'test': 'leave_top5_symbols', 'removed': ['DIG', 'BMP', 'STB', 'GMD', 'HSG'], 'incr': 0.0018789749441917585, 'survived': True}
  - {'test': 'neighbor_horizons_same_sign', 'n_agree': 3, 'survived': True}
  - {'test': 'reverse_feature', 'reverse': 'diverge_buy_down', 'same_direction_effect': np.False_, 'rev_incr': -0.0017982452699599064}
  - {'test': 'drop_strongest_year', 'year': '2009', 'incr': 0.0014640038854879325, 'survived': np.True_}
  - {'test': 'parent_condition', 'parent': 'net_neg', 'parent_incr': -0.00022956726486056303, 'ratio_parent_over_child': 0.10243682231150436}

## FFB1_0069 — `diverge_sell_up` T3
- killed: `False` severity=`None` reason=`None`
- survived_leave_top5: `True`
- survived_alt_horizon: `True`
  - {'test': 'leave_top5_symbols', 'removed': ['HSG', 'GMD', 'VPL', 'VHC', 'STB'], 'incr': 0.0012994486113468273, 'survived': True}
  - {'test': 'neighbor_horizons_same_sign', 'n_agree': 3, 'survived': True}
  - {'test': 'reverse_feature', 'reverse': 'diverge_buy_down', 'same_direction_effect': np.False_, 'rev_incr': -0.0013523890752404}
  - {'test': 'drop_strongest_year', 'year': '2009', 'incr': 0.000934131612327272, 'survived': np.True_}
  - {'test': 'parent_condition', 'parent': 'net_neg', 'parent_incr': -0.0006873537189092333, 'ratio_parent_over_child': 0.29201207523047146}

## FFB1_0070 — `diverge_sell_up` T5
- killed: `True` severity=`soft` reason=`depends_on_year_2009`
- survived_leave_top5: `False`
- survived_alt_horizon: `True`
  - {'test': 'leave_top5_symbols', 'removed': ['HSG', 'GMD', 'SBT', 'BMP', 'KSB'], 'incr': 0.00022253326527117354, 'survived': False}
  - {'test': 'neighbor_horizons_same_sign', 'n_agree': 3, 'survived': True}
  - {'test': 'reverse_feature', 'reverse': 'diverge_buy_down', 'same_direction_effect': np.False_, 'rev_incr': -0.0016556656524256215}
  - {'test': 'drop_strongest_year', 'year': '2009', 'incr': -0.00036214590051491407, 'survived': np.False_}
  - {'test': 'parent_condition', 'parent': 'net_neg', 'parent_incr': -0.001083276658989963, 'ratio_parent_over_child': 0.6643054664859319}

## FFB1_0071 — `diverge_sell_up` T10
- killed: `True` severity=`soft` reason=`depends_on_year_2009`
- survived_leave_top5: `True`
- survived_alt_horizon: `True`
  - {'test': 'leave_top5_symbols', 'removed': ['HSG', 'BMP', 'GMD', 'PET', 'HHS'], 'incr': 0.0007878426349647841, 'survived': True}
  - {'test': 'neighbor_horizons_same_sign', 'n_agree': 3, 'survived': True}
  - {'test': 'reverse_feature', 'reverse': 'diverge_buy_down', 'same_direction_effect': np.False_, 'rev_incr': -0.0016069068847455459}
  - {'test': 'drop_strongest_year', 'year': '2009', 'incr': -0.0020021291935178793, 'survived': np.False_}
  - {'test': 'parent_condition', 'parent': 'net_neg', 'parent_incr': -0.0016533697488451907, 'ratio_parent_over_child': 1.1741049131191628}

## FFB1_0072 — `abn_buy_z15_px_down` T1
- killed: `False` severity=`None` reason=`None`
- survived_leave_top5: `True`
- survived_alt_horizon: `False`
  - {'test': 'leave_top5_symbols', 'removed': ['PTB', 'SSI', 'CMG', 'STB', 'CII'], 'incr': -0.0006861643237535611, 'survived': True}
  - {'test': 'neighbor_horizons_same_sign', 'n_agree': 0, 'survived': False}
  - {'test': 'drop_strongest_year', 'year': '2011', 'incr': -0.00031492961113216303, 'survived': np.True_}
  - {'test': 'parent_condition', 'parent': 'net_pos', 'parent_incr': 0.0002896107233787365, 'ratio_parent_over_child': 0.3495801353290817}

## FFB1_0073 — `abn_buy_z15_px_down` T5
- killed: `True` severity=`soft` reason=`depends_on_year_2014`
- survived_leave_top5: `True`
- survived_alt_horizon: `True`
  - {'test': 'leave_top5_symbols', 'removed': ['CII', 'DIG', 'GAS', 'KBC', 'HDG'], 'incr': 0.00047598835547513316, 'survived': True}
  - {'test': 'neighbor_horizons_same_sign', 'n_agree': 1, 'survived': True}
  - {'test': 'drop_strongest_year', 'year': '2014', 'incr': -0.001057858632394241, 'survived': np.False_}
  - {'test': 'parent_condition', 'parent': 'net_pos', 'parent_incr': 0.0004943137964284101, 'ratio_parent_over_child': 0.7357091927512638}

## FFB1_0074 — `abn_buy_z15_px_down` T10
- killed: `False` severity=`None` reason=`None`
- survived_leave_top5: `True`
- survived_alt_horizon: `False`
  - {'test': 'leave_top5_symbols', 'removed': ['HDG', 'DIG', 'HSG', 'CII', 'BMP'], 'incr': 0.0045775534900269095, 'survived': True}
  - {'test': 'neighbor_horizons_same_sign', 'n_agree': 0, 'survived': False}
  - {'test': 'drop_strongest_year', 'year': '2014', 'incr': 0.0037908660368597127, 'survived': np.True_}
  - {'test': 'parent_condition', 'parent': 'net_pos', 'parent_incr': 0.0006787339959780242, 'ratio_parent_over_child': 0.10773067553748443}

## FFB1_0075 — `abn_sell_z15_px_up` T1
- killed: `False` severity=`None` reason=`None`
- survived_leave_top5: `True`
- survived_alt_horizon: `True`
  - {'test': 'leave_top5_symbols', 'removed': ['GMD', 'BMP', 'IJC', 'SBT', 'CMG'], 'incr': 0.002456340156076661, 'survived': True}
  - {'test': 'neighbor_horizons_same_sign', 'n_agree': 3, 'survived': True}
  - {'test': 'drop_strongest_year', 'year': '2009', 'incr': 0.0028231904093209887, 'survived': np.True_}
  - {'test': 'parent_condition', 'parent': 'net_neg', 'parent_incr': -0.00022956726486056303, 'ratio_parent_over_child': 0.059414135761785565}

## FFB1_0076 — `abn_sell_z15_px_up` T3
- killed: `False` severity=`None` reason=`None`
- survived_leave_top5: `False`
- survived_alt_horizon: `True`
  - {'test': 'leave_top5_symbols', 'removed': ['GMD', 'IJC', 'BMP', 'STB', 'NTL'], 'incr': 0.00046302164517047736, 'survived': False}
  - {'test': 'neighbor_horizons_same_sign', 'n_agree': 3, 'survived': True}
  - {'test': 'drop_strongest_year', 'year': '2009', 'incr': 0.0010799281824221312, 'survived': np.True_}
  - {'test': 'parent_condition', 'parent': 'net_neg', 'parent_incr': -0.0006873537189092333, 'ratio_parent_over_child': 0.213755475919567}

## FFB1_0077 — `abn_sell_z15_px_up` T5
- killed: `True` severity=`soft` reason=`depends_on_year_2009`
- survived_leave_top5: `False`
- survived_alt_horizon: `True`
  - {'test': 'leave_top5_symbols', 'removed': ['GMD', 'HDC', 'BMP', 'STB', 'TCM'], 'incr': -0.0028726173697561364, 'survived': np.False_}
  - {'test': 'neighbor_horizons_same_sign', 'n_agree': 3, 'survived': True}
  - {'test': 'drop_strongest_year', 'year': '2009', 'incr': -0.0019321559387939658, 'survived': np.False_}
  - {'test': 'parent_condition', 'parent': 'net_neg', 'parent_incr': -0.001083276658989963, 'ratio_parent_over_child': 1.5267791933082464}

## FFB1_0078 — `abn_sell_z15_px_up` T10
- killed: `True` severity=`soft` reason=`depends_on_year_2009`
- survived_leave_top5: `True`
- survived_alt_horizon: `True`
  - {'test': 'leave_top5_symbols', 'removed': ['IJC', 'SBT', 'VHC', 'REE', 'STB'], 'incr': 0.004301845457203212, 'survived': True}
  - {'test': 'neighbor_horizons_same_sign', 'n_agree': 2, 'survived': True}
  - {'test': 'drop_strongest_year', 'year': '2009', 'incr': -0.0005172121741851532, 'survived': np.False_}
  - {'test': 'parent_condition', 'parent': 'net_neg', 'parent_incr': -0.0016533697488451907, 'ratio_parent_over_child': 0.5870117509830733}

## FFB1_0079 — `abn_buy_z15_px_up` T1
- killed: `False` severity=`None` reason=`None`
- survived_leave_top5: `True`
- survived_alt_horizon: `True`
  - {'test': 'leave_top5_symbols', 'removed': ['BVH', 'VHC', 'MSN', 'KBC', 'NTL'], 'incr': 0.002914207596996961, 'survived': True}
  - {'test': 'neighbor_horizons_same_sign', 'n_agree': 3, 'survived': True}
  - {'test': 'drop_strongest_year', 'year': '2009', 'incr': 0.0027206271326348373, 'survived': np.True_}
  - {'test': 'parent_condition', 'parent': 'net_pos', 'parent_incr': 0.0002896107233787365, 'ratio_parent_over_child': 0.07901255981394978}

## FFB1_0080 — `abn_buy_z15_px_up` T3
- killed: `False` severity=`None` reason=`None`
- survived_leave_top5: `True`
- survived_alt_horizon: `True`
  - {'test': 'leave_top5_symbols', 'removed': ['BVH', 'VHC', 'KSB', 'KBC', 'MSN'], 'incr': 0.002818455577806012, 'survived': True}
  - {'test': 'neighbor_horizons_same_sign', 'n_agree': 3, 'survived': True}
  - {'test': 'drop_strongest_year', 'year': '2009', 'incr': 0.0029647223904458397, 'survived': np.True_}
  - {'test': 'parent_condition', 'parent': 'net_pos', 'parent_incr': 0.0003422908375673555, 'ratio_parent_over_child': 0.07623922995183217}

## FFB1_0081 — `abn_buy_z15_px_up` T5
- killed: `False` severity=`None` reason=`None`
- survived_leave_top5: `False`
- survived_alt_horizon: `True`
  - {'test': 'leave_top5_symbols', 'removed': ['BVH', 'BMP', 'BSI', 'VHC', 'IJC'], 'incr': 0.002164097593905473, 'survived': False}
  - {'test': 'neighbor_horizons_same_sign', 'n_agree': 3, 'survived': True}
  - {'test': 'drop_strongest_year', 'year': '2009', 'incr': 0.0017556097215545568, 'survived': np.True_}
  - {'test': 'parent_condition', 'parent': 'net_pos', 'parent_incr': 0.0004943137964284101, 'ratio_parent_over_child': 0.1068413646870595}

## FFB1_0082 — `abn_buy_z15_px_up` T10
- killed: `False` severity=`None` reason=`None`
- survived_leave_top5: `True`
- survived_alt_horizon: `True`
  - {'test': 'leave_top5_symbols', 'removed': ['BVH', 'BMP', 'SBT', 'STB', 'KBC'], 'incr': 0.0038441439286133845, 'survived': True}
  - {'test': 'neighbor_horizons_same_sign', 'n_agree': 3, 'survived': True}
  - {'test': 'drop_strongest_year', 'year': '2009', 'incr': 0.0025469794922310437, 'survived': np.True_}
  - {'test': 'parent_condition', 'parent': 'net_pos', 'parent_incr': 0.0006787339959780242, 'ratio_parent_over_child': 0.12088330186278738}

## FFB1_0083 — `abn_sell_z15_px_down` T5
- killed: `True` severity=`soft` reason=`simpler_parent_explains`
- survived_leave_top5: `True`
- survived_alt_horizon: `True`
  - {'test': 'leave_top5_symbols', 'removed': ['DPM', 'VHC', 'KBC', 'VTO', 'STB'], 'incr': -0.0009111144578562695, 'survived': True}
  - {'test': 'neighbor_horizons_same_sign', 'n_agree': 2, 'survived': True}
  - {'test': 'drop_strongest_year', 'year': '2011', 'incr': 0.002215155445834783, 'survived': np.False_}
  - {'test': 'parent_condition', 'parent': 'net_neg', 'parent_incr': -0.001083276658989963, 'ratio_parent_over_child': 2.0740089846816723}

## FFB1_0084 — `abn_sell_z15_px_down` T10
- killed: `True` severity=`soft` reason=`simpler_parent_explains`
- survived_leave_top5: `True`
- survived_alt_horizon: `True`
  - {'test': 'leave_top5_symbols', 'removed': ['BMP', 'KBC', 'VCB', 'HDC', 'VPL'], 'incr': -0.0030324135374612273, 'survived': True}
  - {'test': 'neighbor_horizons_same_sign', 'n_agree': 3, 'survived': True}
  - {'test': 'drop_strongest_year', 'year': '2011', 'incr': 0.004498943575941775, 'survived': np.False_}
  - {'test': 'parent_condition', 'parent': 'net_neg', 'parent_incr': -0.0016533697488451907, 'ratio_parent_over_child': 3.1856791030958855}


## Parent horse-race audit (post-screen)

Price-alone (`px_pos`/`px_neg`) explains most of `agree_*` effects in validation; conditional foreign-flow incremental given price is unstable/near-zero. Those interaction candidates were downgraded to FRAGILE and are **not** claimed as foreign-flow information.

`abn_abs_z20` at T10 retained as RESEARCH_CANDIDATE (magnitude, not sign).
