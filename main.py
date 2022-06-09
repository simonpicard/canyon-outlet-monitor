# -*- coding: utf-8 -*-

"""Scrap Canyon outlet and send mail with bikes matching a search."""

import datetime
import logging
import os
import sys

import htmlmin
import pandas as pd
import requests
import yagmail
import yaml
from bs4 import BeautifulSoup
from yaml import Loader

feature_cols = [
    "product_name",
    "product_price",
    "product_price_new",
    "product_size",
    "product_color",
    "pid",
    "url",
    "currency",
    "active",
]

logger = logging.getLogger()
logger.setLevel(logging.INFO)

console = logging.StreamHandler()
logger.addHandler(console)


def parse_elem(elem):
    """Parse a single bike HTML element into a pd.Series.

    Args:
        elem (BeautifulSoup document): a single bike HTML element

    Returns:
        pd.Series: parsed bike HMTL element
    """
    res = pd.Series()
    res["product_name"] = elem.find(
        "div", "productTile__productName"
    ).text.strip()
    res["product_price"] = elem.find(
        "div", "productTile__priceSale"
    ).text.strip()
    res["product_price_new"] = elem.find(
        "div", "productTile__priceOriginal"
    ).text.strip()
    try:
        res["product_size"] = elem.find(
            "div", "productTile__size"
        ).text.strip()
    except Exception:
        res["product_size"] = "multi"
    res["product_color"] = elem.find("button", "colorSwatch")["title"].strip()
    res["pid"] = elem.find("div", "productTile")["data-pid"].strip()
    res["url"] = elem.find("a", "productTile__link")["href"].strip()
    return res


def post_process(df):
    """Apply post processing to bike pd.DataFrame.

    Args:
        df (pd.DataFrame): outlet's bike dataframe.

    Returns:
        pd.DataFrame: post processed outlet's bike dataframe.
    """
    df["currency"] = df["product_price"].str.extract("([$€£¥])")
    df["product_price"] = pd.to_numeric(
        df["product_price"]
        .str.extract("([\d\.,]+)")[0]
        .str.replace(".", "", regex=False)
        .str.replace(",", ".", regex=False)
    )
    df["product_price_new"] = pd.to_numeric(
        df["product_price_new"]
        .str.extract("([\d\.,]+)")[0]
        .str.replace(".", "", regex=False)
        .str.replace(",", ".", regex=False)
    )
    absolute_link_scope = df["url"].str.contains("^http")
    df.loc[~absolute_link_scope, "url"] = (
        "https://www.canyon.com" + df.loc[~absolute_link_scope, "url"]
    )

    df["active"] = True
    df["date_scrapped"] = datetime.datetime.now()

    return df


def parse_outlet():
    """Parse the Canyon outlet's HTML page.

    Returns:
        pd.DataFrame: current outlet's bike dataframe.
    """
    logging.info("Scrapping...")
    outlet_url = "https://www.canyon.com/fr-be/promo-velos/?searchredirect=false&searchType=outlet&start=0&sz=1000"
    outlet_html = requests.get(outlet_url)
    soup = BeautifulSoup(outlet_html.text, "html.parser")

    elems = soup.find_all("li", "productGrid__listItem xlt-producttile")
    df = pd.Series(elems).apply(parse_elem)

    df = post_process(df)

    logging.info(f"Found {df.shape[0]} bikes.")
    return df


def update_bikes(df, df_old):
    """Update the full oulet's bike database.

    Args:
        df (pd.DataFrame): The current outlet's bike dataframe.
        df_old (pd.DataFrame): The previous outlet's bike dataframe.

    Returns:
        pd.DataFrame: the updated outlet's bike dataframe.
    """
    df_active = df_old.loc[df_old["active"]].merge(
        df, on=feature_cols, how="outer", indicator="Exist"
    )
    df_active["active"] = True
    df_active["new"] = df_active["Exist"] == "right_only"
    df_active["date_scrapped"] = df_active["date_scrapped_x"].combine_first(
        df_active["date_scrapped_y"]
    )

    df_active = df_active[df_old.columns]

    df_all = df_old.loc[~df_old["active"]].append(df_active, ignore_index=True)

    logging.info(f'{df_all["new"].sum()} new bikes.')

    return df_all


def search_bikes(df, searches):
    """Search bikes based on search criteria.

    Args:
        df (pd.DataFrame): a outlet's bike dataframe.'
        searches (dict): the dict of regex to search for

    Returns:
        pd.DataFrame: the dataframe with bikes matching search.
    """
    results = pd.DataFrame()
    if not df.empty:
        for search in searches:
            scope = pd.Series([True] * df.shape[0], index=df.index)
            for col, regex in search.items():
                scope &= df[col].str.contains(regex, case=False)
            results = results.append(df.loc[scope], ignore_index=True)
    return results


def mail_notifications(df, receiver, sender, pw):
    """Send email notifications to the receiver.

    Args:
        df (pd.DataFrame): The bike dataframe to send by email notification.
        receiver (str): the email of the sender, must be Gmail
        sender (str): the email of the reciever
        pw (str): the password of the sender
    """
    if not df.empty:
        df = df.copy()
        df["url"] = '<a href="' + df["url"] + '">link</a>'

        table_html = (
            "<div> <style scoped> .dataframe{border-collapse: collapse;"
            " margin: 25px 0; font-size: 0.9em; font-family: sans-serif;"
            " min-width: 400px; box-shadow: 0 0 20px rgba(0, 0, 0,"
            " 0.15);}.dataframe thead tr{background-color: #009879; color:"
            " #ffffff; text-align: left;}.dataframe th, .dataframe td{padding:"
            " 12px 15px;}.dataframe tbody tr{border-bottom: 1px solid"
            " #dddddd;}.dataframe tbody tr:nth-of-type(even){background-color:"
            " #f3f3f3;}.dataframe tbody tr:last-of-type{border-bottom: 2px"
            " solid #009879;}.dataframe tbody tr.active-row{font-weight: bold;"
            " color: #009879;}</style>"
        )
        table_html += df.to_html(index=False, escape=False)
        table_html += "</div>"

        subject = f"Canyon Outlet: {df.shape[0]} new match"
        body = "Canyon Outlet monitoring\n\n"
        body += htmlmin.minify(table_html)

        yag = yagmail.SMTP(sender, pw)
        yag.send(to=receiver, subject=subject, contents=body)

        logging.info("Mail sent.")


def pubsub_trigger(event, context):
    """Triggered from a message on a Cloud Pub/Sub topic.

    Args:
         event (dict): Event payload.
         context (google.cloud.functions.Context): Metadata for the event.
    """
    cfg_path = "conf/config.yaml"
    main(cfg_path)


def main(cfg_path):
    """Execute the main.

    Args:
        cfg_path (str): the path to the config file.
    """
    with open(cfg_path, "r") as f:
        cfg = yaml.load(f, Loader=Loader)

    if cfg["bikes_df"]["gcs"] and not cfg["bikes_df"]["cloud_function"]:
        cwd = os.getcwd()
        sa_path = os.path.join(cwd, cfg["bikes_df"]["sa_path"])
        os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = sa_path

    df = parse_outlet()
    df_old = pd.read_csv(cfg["bikes_df"]["path"])

    df_all = update_bikes(df, df_old)

    search_results = search_bikes(df_all[df_all["new"]], cfg["search"])

    logging.info(f"{search_results.shape[0]} match search.")

    mail_notifications(
        search_results,
        cfg["mail"]["receiver"],
        cfg["mail"]["sender"],
        cfg["mail"]["pw"],
    )

    if df_all["new"].any():
        df_all.to_csv(cfg["bikes_df"]["path"], index=False)
        logging.info("Saved bikes records.")


if __name__ == "__main__":

    cfg_path = sys.argv[1]
    main(cfg_path)
