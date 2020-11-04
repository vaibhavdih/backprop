from typing import Callable, Dict, List
from sentence_transformers import SentenceTransformer

from .search import DocStore, SearchResults, Document
from .utils import process_document, process_results


class Kiri:
    """Core class of natural language engine
    
    Attributes:
        store: DocStore object to be used as the engine backend
        vectorize_model: Name of the SentenceTransformer model to be used in operations
        process_doc_func: Function to be used when vectorizing updloaded documents
        process_results_func: Function to be used for calculating final scores of results
    
    Raises:
        ValueError: If a DocStore is not provided
    """

    def __init__(self, store: DocStore, vectorize_model: str = None,
                 process_doc_func: Callable[[
                     Document, SentenceTransformer], List[float]] = None,
                 process_results_func: Callable[[SearchResults, SentenceTransformer], None] = None):

        if store is None:
            raise ValueError("a DocStore implementation must be provided")

        if vectorize_model is None:
            # Use default vectorization model
            vectorize_model = "distiluse-base-multilingual-cased-v2"

        if process_doc_func is None:
            # Use default vectorizer
            process_doc_func = process_document

        if process_results_func is None:
            process_results_func = process_results

        self._store = store
        self._process_doc_func = process_doc_func
        self._process_results_func = process_results
        self._vectorize_model = SentenceTransformer(vectorize_model)

    def upload(self, documents: List[Document]) -> None:
        """Uploads documents to store

        Args:
            documents: List of documents for upload

        """

        return self._store.upload(documents, self._process_doc_func,
                                  self._vectorize_model)

    def search(self, query: str, max_results=10, min_score=0.0,
               preview_length=100, ids=None, body=None) -> SearchResults:
        """Search documents from document store

        Args:
            query: Search string on which search is performed
            max_results: Maximum amount of documents to be returned from search
            min_score: Minimum score required to be included in results
            preview_length: Number of characters in the preview/metatext of results
            ids: 
            body: Elasticsearch request body to be passed to the backend

        """
        search_results, query_vec = self._store.search(query, self._vectorize_model,
                                                       max_results=max_results, min_score=min_score,
                                                       ids=ids, body=body)
        self._process_results_func(
            search_results, query_vec, self._store._doc_class, preview_length)
        return search_results
