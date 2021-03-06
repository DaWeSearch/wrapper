#!/usr/bin/env python3

import re
from typing import Union

import requests

from .wrapperInterface import WrapperInterface

class ElsevierWrapper(WrapperInterface):
	def __init__(self, apiKey: str):
		self.apiKey = apiKey

		self.__resultFormat = "application/json"

		self.__collection = "search/sciencedirect"

		self.__startRecord = 1

		self.__parameters = {}

	# Endpoint used for the query
	@property
	def endpoint(self) -> str:
		return "https://api.elsevier.com/content"

	# A dictionary that contains the available result formats for each collection
	@property
	def allowedResultFormats(self) -> {str: [str]}:
		return {
			"search/sciencedirect": ["application/json"],
			"metadata/article": ["application/json", "application/atom+xml", "application/xml"]
		}

	# The result format that will be used for the query
	@property
	def resultFormat(self) -> str:
		return self.__resultFormat

	# resultFormat must be settable
	@resultFormat.setter
	def resultFormat(self, value: str):
		# strip leading and trailing whitespace and convert to lower case
		value = str(value).strip().lower()

		if value in self.allowedResultFormats[self.collection]:
			self.__resultFormat = value
		elif ("application/" + value) in self.allowedResultFormats[self.collection]:
			print(f"Assumed you meant application/{value}")
			self.__resultFormat = "application/" + value
		else:
			raise ValueError(f"Illegal format {value} for collection {self.collection}")

	# Collection being used for the query
	@property
	def collection(self) -> str:
		return self.__collection

	# collection must be settable
	@collection.setter
	def collection(self, value: str):
		# strip leading and trailing whitespace and convert to lower case
		value = str(value).strip().lower()

		if not value in self.allowedResultFormats:
			raise ValueError(f"Unknown collection {value}")

		self.__collection = value

	# Maximum number of results that the API will return
	@property
	def maxRecords(self) -> int:
		return int(self.allowedDisplays["show"][-1])
		# return 100

	# Dictionary of allowed keys and their allowed values for searchField()
	@property
	def allowedSearchFields(self) -> {str: [str]}:
		# TODO: allow regex constraints
		return {
			"author": [], "date": [], "highlights": ["true", "false"],
			"openAccess": ["true", "false"], "issue": [], "loadedAfter": [],
			"page": [], "pub": [], "qs": [], "title": [], "volume": []
		}

	# Dictionary of allowed "display" settings
	@property
	def allowedDisplays(self) -> {str: [str]}:
		return {
			"offset": [], "show": ["10", "25", "50", "100"],
			"sortBy": ["relevance", "date"]
		}

	# Specify value for a given search parameter for manual search
	def searchField(self, key: str, value, parameters: {str, str} = None):
		# (not parameters) returns True if dict is empty
		if parameters == None:
			parameters = self.__parameters

		# convert to lowercase and strip leading and trailing whitespace
		key = str(key).strip().lower()
		value = str(value).strip()
		if len(value) == 0:
			raise ValueError(f"Value is empty")

		# are key and value allowed (as combination)?
		# TODO: allow regex constraints
		if key in self.allowedSearchFields:
			if len(self.allowedSearchFields[key]) == 0 or value in self.allowedSearchFields[key]:
				parameters[key] = value
			else:
				raise ValueError(f"Illegal value {value} for search-field {key}")
		else:
			raise ValueError(f"Searches against {key} are not supported")

	# Reset a search parameter
	def resetField(self, key: str):
		if key in self.__parameters:
			del self.__parameters[key]
		else:
			raise ValueError(f"Field {key} is not set.")

	# Build url and headers needed
	def buildQuery(self) -> (str, {str: str}):
		url = self.endpoint
		url += "/" + str(self.collection)

		headers = {"X-ELS-APIKey": self.apiKey, "Accept": self.resultFormat}

		return url, headers

	# Builds a search group by inserting the connector between the search terms
	def buildGroup(self, items: [str], connector: str) -> str:
		group = "("

		# connect with OR and negate group if connector is NOT
		if connector == "NOT":
			group = "NOT " + group
			connector = "OR"

		# Insert and combine
		group += (" " + connector + " ").join(items)

		group += ")"
		return group

	# Translate a search in the wrapper input format into a query that the wrapper api understands
	def translateQuery(self, query: dict) -> {str: str}:
		params = {}

		groups = query["search_groups"].copy()
		for i in range(len(groups)):
			groups[i] = self.buildGroup(groups[i]["search_terms"], groups[i]["match"])
		groups = self.buildGroup(groups, query["match"])
		try:
			self.searchField("qs", groups, parameters=params)
		except ValueError as e:
			print(e)

		return params

	# Set the index from which the returned results start
	# (Necessary if there are more hits for a query than the maximum number of returned results.)
	def startAt(self, value: int):
		self.__startRecord = int(value)

	# Format the returned json
	def formatResponse(self, response: requests.Response, query: str, body: {str: str}):
		if self.resultFormat == "application/json":
			# Load into dict
			response = response.json()

			# Modify response to fit the defined wrapper output format
			response["query"] = query
			response["dbquery"] = body
			response["apiKey"] = self.apiKey
			response["result"] = {
				"total": response.pop("resultsFound"),
				"start": self.__parameters["offset"] if "offset" in self.__parameters else 1,
				"pageLength": self.__parameters["show"] if "show" in self.__parameters else 25,
				"recordsDisplayed": len(response["results"])
			}
			response["records"] = response.pop("results")
			for record in response["records"]:
				authors = []
				for author in record["authors"]:
					authors.append(author["name"])
				record["authors"] = authors
				record["publicationName"] = record.pop("sourceTitle")
				record["publisher"] = "ScienceDirect"

			return response
		else:
			print(f"No formatter defined for {self.resultFormat}. Returning raw response.")
			return response.text

	# Make the call to the API
	# If no query is given, use the manual search specified by searchField() calls
	def callAPI(self, query: Union[dict, None] = None, raw: bool = False, dry: bool = False):
		if not query:
			body = self.__parameters
		else:
			body = self.translateQuery(query)

		if not body:
			raise ValueError("No search-parameters set.")
		body["display"] = {
			"offset": self.__startRecord,
			"show": self.maxRecords
		}

		url, headers = self.buildQuery()

		if dry:
			return url, headers, body

		response = requests.put(url, headers=headers, json=body)
		if raw:
			return response.text
		return self.formatResponse(response, query, body)

