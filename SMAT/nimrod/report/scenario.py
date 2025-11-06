import os
import csv
from csv import reader

class Scenario:

    def __init__(self, scenario, list_suites):
        self.scenario = scenario
        self.test_suites = list_suites
        self.evosuite_test_suites = self.get_suites_for_specific_tool(self.test_suites, "evosuite")
        self.diff_evosuite_test_suites = self.get_suites_for_specific_tool(self.test_suites, "differential-evosuite")
        self.randoop_test_suites = self.get_suites_for_specific_tool(self.test_suites, "randoop")
        # did the first suit detect the semantic conflict?
        self.evosuite_first_suite_detection = self.check_if_first_suite_detects_behavior_change(self.evosuite_test_suites)
        self.diff_evosuite_first_suite_detection = self.check_if_first_suite_detects_behavior_change(self.diff_evosuite_test_suites)
        self.randoop_first_suite_detection = self.check_if_first_suite_detects_behavior_change(self.randoop_test_suites)
        # any of the previous one
        self.general_first_suite_detection = (self.diff_evosuite_first_suite_detection or self.evosuite_first_suite_detection or self.randoop_first_suite_detection)
        # number of suites that detected the semantic conflicts
        self.evosuite_detected_sm_by_suites = self.check_detected_behavior_changes_by_suites(self.evosuite_test_suites)
        self.diff_evosuite_detected_sm_by_suites = self.check_detected_behavior_changes_by_suites(self.diff_evosuite_test_suites)
        self.randoop_detected_sm_by_suites = self.check_detected_behavior_changes_by_suites(self.randoop_test_suites)
        self.general_detected_sm_by_suites = self.evosuite_detected_sm_by_suites + self.diff_evosuite_detected_sm_by_suites + self.randoop_detected_sm_by_suites
        # number of call performed until the first suit detected the semantic conflict
        self.evosuite_detected_sm_until_first = self.check_first_suit_of_detected_behavior_changes(self.evosuite_test_suites)
        self.diff_evosuite_detected_sm_until_first = self.check_first_suit_of_detected_behavior_changes(self.diff_evosuite_test_suites)
        self.randoop_detected_sm_until_first = self.check_first_suit_of_detected_behavior_changes(self.randoop_test_suites)
        # mean of calls performed to detect semantic conflict
        if (len(self.evosuite_test_suites)):
            self.mean_evosuite_detected_sm_calls = self.evosuite_detected_sm_by_suites/len(self.evosuite_test_suites)
        if (len(self.diff_evosuite_test_suites)):
            self.mean_diff_evosuite_detected_sm_calls = self.diff_evosuite_detected_sm_by_suites/len(self.diff_evosuite_test_suites)
        if (len(self.randoop_test_suites)):
            self.mean_randoop_detected_sm_calls = self.randoop_detected_sm_by_suites/len(self.randoop_test_suites)

    def get_suites_for_specific_tool(self, suites, tool):
        suites_for_tool = []
        for suite in suites:
            if (suite[4] == tool):
                suites_for_tool.append(suite)

        return suites_for_tool

    def check_if_first_suite_detects_behavior_change(self, suites):
        if (len(suites) > 0):
            if suites[0][5] == "True":
                return True

        return False

    def check_detected_behavior_changes_by_suites(self, suites):
        detected_behavior = 0
        for suite in suites:
            if suite[5] == "True":
                detected_behavior += 1

        return detected_behavior

    def check_first_suit_of_detected_behavior_changes(self, suites):
        suite_id = 0
        index = 0
        for suite in suites:
            index += 1
            if suite[5] == "True":
                suite_id = index
                break

        return suite_id