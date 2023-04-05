import hashlib
import json
import logging

from matplotlib.pyplot import axis
import pandas as pd 
import os
import re
import string

import nltk
import numpy as np
import pandas as pd

from collections import Counter 

from nltk import word_tokenize
from nltk.corpus import stopwords

from sklearn.cluster import MiniBatchKMeans, DBSCAN
from sklearn.metrics import silhouette_samples, silhouette_score

import app_logger
from ds_utils.config import set_display_options, set_random_seed
from ds_utils.clustering import Tokenizer, load_data, clean_news_data, vectorize, mbkmeans_clusters

import gensim.downloader as api
from gensim.models import Doc2Vec
import gensim.models as gensim_models
from sklearn.feature_extraction.text import TfidfVectorizer
from simhash import Simhash
from scipy.spatial import distance


# TODO check the state of the art for doc clustering. Why not using BERT or something like that? 
def get_column_content(df_col):
    return ' '.join(df_col)

nltk.download("stopwords")


def get_df_headers(table_path):
    df = pd.read_csv(table_path)
    return ' '.join(df.columns)


def get_context_df(sandbox_path):
    context_dict = {'table_id': [], 'parent': [], 'table_name': [], 'headers': [], 'content': []}
    sandbox_children = os.listdir(sandbox_path)
    sandbox_children.sort()
    table_id = 0
    total_num_cells = 0
    for child_name in sandbox_children:
        if not child_name.startswith("."):
            child_path = os.path.join(sandbox_path, child_name)
            tables_dirs = os.listdir(child_path)
            tables_dirs.sort()
            for table in tables_dirs:
                if not table.startswith("."):
                    table_path = os.path.join(child_path, table)
                    df_path = os.path.join(table_path, "dirty_clean.csv")
                    df_text_columns = pd.read_csv(df_path)
                    total_num_cells += df_text_columns.size
                    df_text_columns = df_text_columns.select_dtypes(include=object)
                    df_table_text = ""

                    for index, row in df_text_columns.iterrows():
                        df_table_text = ' '.join(row.astype(str).tolist())

                    # for column in df_text_columns.columns:
                    #     col_text = ' '.join(df_text_columns[column].astype(str).tolist())
                    #     df_table_text += col_text

                    context_dict['table_id'].append(table_id)
                    context_dict['parent'].append(child_name)
                    context_dict['table_name'].append(table)
                    context_dict['headers'].append(get_df_headers(os.path.join(table_path, "dirty_clean.csv")))
                    context_dict['content'].append(df_table_text)
                    table_id += 1
    context_df = pd.DataFrame.from_dict(context_dict)
    return context_df, total_num_cells


def clean_text(text, tokenizer, stopwords):
    """Pre-process text and generate tokens

    Args:
        text: Text to tokenize.

    Returns:
        Tokenized text.
    """
    text = ''.join(word.strip(string.punctuation) for word in text)
    text = str(text).lower()  # Lowercase words
    text = re.sub(r"\[(.*?)\]", "", text)  # Remove [+XYZ chars] in content
    text = re.sub(r"\s+", " ", text)  # Remove multiple spaces in content
    text = re.sub(r"\w+…|…", "", text)  # Remove ellipsis (and last word)
    text = re.sub(r"(?<=\w)-(?=\w)", " ", text)  # Replace dash between words
    text = re.sub(
        f"[{re.escape(string.punctuation)}]", "", text
    )  # Remove punctuation

    tokens = tokenizer(text)  # Get tokens from text
    tokens = [t.encode('ascii', errors='ignore').decode("utf-8") for t in tokens]  # Remove non-ascii characters
    for i in range(len(tokens)):
        for t in tokens[i]:
            if t in string.punctuation:
                tokens[i].replace(t, '')
            if t.isdigit():
                tokens[i].replace(t, '')
    tokens = [t for t in tokens if t not in stopwords]  # Remove stopwords
    tokens = ["" if t.isdigit() else t for t in tokens]  # Remove digits
    tokens = [t for t in tokens if len(t) > 1]  # Remove short tokens
    return tokens


def vectorize(list_of_docs, tf_idf_res, model):
    """Generate vectors for list of documents using a Word Embedding

    Args:
        list_of_docs: List of documents
        model: Gensim's Word Embedding

    Returns:
        List of document vectors
    """
    features = []

    for i in range(len(list_of_docs)):
        tokens = list_of_docs[i].split()
        weights = tf_idf_res[i]
        zero_vector = np.zeros(model.vector_size)
        vectors = []
        vectors_weights = []
        
        for j in range(len(tokens)):
            if tokens[j] in model and len(tokens[j]) > 1:
                try:
                    vectors.append(model[tokens[j]])
                    vectors_weights.append(weights[tokens[j]])
                except KeyError as e:
                    print(e)
        if vectors:
            # weighted_features = []
            # for v_idx in range(len(vectors)):
            #     weighted_features.append(vectors[v_idx] * vectors_weights[v_idx])
            # weighted_features = np.asarray(weighted_features)
            # avg_vec = weighted_features.mean(axis=0)
            avg_vec = np.average(vectors, weights=vectors_weights, axis=0)
            features.append(avg_vec)
        else:
            features.append(zero_vector)
    return features

def tfidf(list_of_docs):
    non_tokenized_docs = []
    for i in range(len(list_of_docs)):
        non_tokenized_docs.append(' '.join(list_of_docs[i]))
    vectorizer = TfidfVectorizer(
    stop_words= None)

    X = vectorizer.fit_transform(non_tokenized_docs)
    doc_word_tfidf_dicts = []
    for doc in non_tokenized_docs:
        X = vectorizer.transform([doc])
        word_tfidf_dict = {}
        feature_names = vectorizer.vocabulary_
        for i, word in enumerate(doc.split()):
            word_tfidf_dict[word] = X[0, feature_names[word]]
        doc_word_tfidf_dicts.append(word_tfidf_dict)

    return doc_word_tfidf_dicts, X.toarray()

def simhash(doc_tokens, doc_word_tfidf_dict):
    """
    Calculates the Simhash of a given text using TF-IDF weights.
    """
    # TODO test this 
    v = [0] * 64

    # for token in doc_tokens:
    #     hash_value = int(hashlib.sha1(token.encode('utf-8')).hexdigest(), 16)
    #     weight = doc_word_tfidf_dict[token]
    #     for i in range(64):
    #         if hash_value & (1 << i):
    #             v[i] += weight
    #         else:
    #             v[i] -= weight
    # simhash = []
    # for i in range(64):
    #     if v[i] >= 0:
    #         simhash.append(1)
    #     else:
    #         simhash.append(0)
    return ''.join([str(x) for x in simhash])

def cluster_datasets(sandbox_path, output_path, auto_clustering_enabled):
    logger = logging.getLogger()

    custom_stopwords = set(stopwords.words("english"))
    context_df, total_num_cells = get_context_df(sandbox_path)

    df = context_df.copy()
    df = df.fillna("")

    text_columns = ["parent", "table_name", "headers", "content"]
    for col in text_columns:
        df[col] = df[col].astype(str)

    # Create text column based on parent, table_name, and headers
    # TODO: check licence
    df["text"] = df[text_columns].apply(lambda x: " | ".join(x), axis=1)
    df["tokens"] = df["text"].map(lambda x: clean_text(x, word_tokenize, custom_stopwords))

    # Remove duplicated after preprocessing
    _, idx = np.unique(df["tokens"], return_index=True)
    df = df.iloc[idx, :]

    # Remove empty values
    df = df.loc[df.tokens.map(lambda x: len(x) > 0), ["text", "tokens"]]

    logger.info(f"Original dataframe: {context_df.shape}")
    logger.info(f"Pre-processed dataframe: {df.shape}")

    docs = df["text"].values
    tokenized_docs = df["tokens"].values
    vocab = Counter()
    for token in tokenized_docs:
        vocab.update(token)

    logger.info(f"Most common vocabs are: {vocab.most_common(10)}")

    if auto_clustering_enabled == "True":
        # TODO: embedding model and DBSCAN params in config file
        # model = Word2Vec(sentences=tokenized_docs, vector_size=100, workers=1, seed=42)
        logger.info("Loading Doc2Vec model")
        model = Doc2Vec.load("/home/fatemeh/pretrained_models/enwiki_20180420_100d.pkl")
        logger.info("Loading Doc2Vec model finished")
        vectorized_docs = [model.infer_vector(' '.join([token for token in doc])) for doc in tokenized_docs]
        # model = api.load('word2vec-google-news-300')
        # tf_idf_res = tfidf(tokenized_docs)
        # vectorized_docs = vectorize(tokenized_docs, tf_idf_res, model=model)
        # vectorized_docs_2 = get_hashed_features(docs)
        # clustering = DBSCAN(eps=0.2, min_samples=2).fit(vectorized_docs) 
        clustering = MiniBatchKMeans(n_clusters=4).fit(vectorized_docs)
        cluster_labels = clustering.labels_

        # doc_word_tfidf_dicts, dense_matrix = tfidf(tokenized_docs)
        # simhashes = [simhash(tokenized_docs[i], doc_word_tfidf_dicts[i]) for i in range(len(tokenized_docs))]
        simhashes = [Simhash(''.join(doc)).value for doc in tokenized_docs]
            
        hamming_distances = dict()
        for i in range(len(simhashes)):
            for j in range(i+1, len(simhashes)):
                hamming_distances[(i, j)] = bin(simhashes[i] ^ simhashes[j]).count('1')
                # distance_ = distance.hamming(list(simhashes[i]), list(simhashes[j]))
                # hamming_distances[(i, j)] = distance_
        print(hamming_distances)
        return 0
    else:
        logger.info("Auto clustering is disabled")
        cluster_labels = np.ones(len(tokenized_docs)).tolist()

    df_clusters = pd.DataFrame({
        "text": docs,
        "tokens": [" ".join(text) for text in tokenized_docs],
        "cluster": cluster_labels
    })
    num_clusters = len(set(cluster_labels))
    logger.info(f"Number of table clusters: {num_clusters}")

    # TODO: Change join
    context_df = context_df.join(df_clusters)
    context_df.to_csv(output_path)

    dict_nums = {"num_clusters": str(num_clusters), "total_num_cells": str(total_num_cells)}
    with open("nums.json", "w", encoding="utf8") as filehandler:
        filehandler.write(json.dumps(dict_nums))

    return context_df, num_clusters, total_num_cells
