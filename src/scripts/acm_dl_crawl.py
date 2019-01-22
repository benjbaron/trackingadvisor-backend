from bs4 import BeautifulSoup, Tag, NavigableString, Comment
import requests
import time
import os
from random import randint

URL_BASE = 'https://dl.acm.org/'
PDF_FOLDER = '/home/ucfabb0/semantica/pdf/'
PROCEEDINGS_LIST = PDF_FOLDER + 'ACM_PAPERS.tsv'  # compiled from https://dl.acm.org/proceedings.cfm
PROCEEDINGS_PDF_URLS = PDF_FOLDER + 'ACM_PAPERS_URLS.tsv'
PROCEEDINGS_PDF_DONE = PDF_FOLDER + 'ACM_PAPERS_URLS_DONE.tsv'
USER_AGENT = 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_14_1) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/70.0.3538.110 Safari/537.36'
MAX_NB_ATTEMPTS = 1000

url_list = []
with open(PROCEEDINGS_LIST, 'r') as f:
    f.readline()
    for line in f:
        fields = line.strip().split('\t')
        acc = fields[1]
        year = int(fields[2])
        folder = PDF_FOLDER + fields[5]
        url = fields[4] + '&preflayout=flat'
        url_list.append({
            'acc': acc,
            'year': year,
            'folder': folder,
            'url': url
        })
print("Done with %s proceedings" % len(url_list))


def get_soup(session, url):
    result = session.get(url)
    soup = BeautifulSoup(result.text, 'html.parser')
    return soup


def replace_characters(text):
    for ch in ['\\', '/', '?', '*', '%', ':', '|', '"', '<', '>', '.']:
        if ch in text:
            text = text.replace(ch, '')
    return text


def retrieve_pdf_files(session, url, folder):
    if not os.path.exists(folder):
        os.makedirs(folder)

    soup = get_soup(session, url)

    for e in soup.find_all('a', {"name": "FullTextPDF"}):
        tr_pdf = e.findParent('tr')
        tr_doi = tr_pdf.find_previous_sibling('tr')
        tr_pp = tr_doi.find_previous_sibling('tr')
        tr_authors = tr_pp.find_previous_sibling('tr')
        tr_title = tr_authors.find_previous_sibling('tr')
        title = tr_title.find('a').getText()
        filename = replace_characters(title.split(':')[0])

        time.sleep(0.25)
        url = URL_BASE + e['href']
        response = session.get(url)

        with open(folder + "/" + filename + '.pdf', 'wb') as f:
            f.write(response.content)


def _retreive_pdf():
    session = requests.Session()
    session.headers.update({'User-Agent': USER_AGENT})

    count = 0
    for e in url_list:
        print(str(count) + " - " + e['acc'] + " @ " + str(e['year']))
        url = e['url']
        folder = e['folder']
        retrieve_pdf_files(session, url, folder)
        count += 1


def _main():
    path_set = set()
    count = 0
    nb_attempts = 0

    done_urls = set()
    if os.path.isfile(PROCEEDINGS_PDF_DONE):
        with open(PROCEEDINGS_PDF_DONE, 'r') as f:
            for line in f:
                done_urls.add(line.strip())

    session = requests.Session()
    session.headers.update({'User-Agent': USER_AGENT})

    with open(PROCEEDINGS_PDF_URLS, 'r') as f:
        for line in f:
            fields = line.strip().split('\t')
            if len(fields) < 5:
                continue
                
            folder = fields[0]
            url = fields[1]
            title = fields[2]
            filename = fields[3]
            doi = fields[4]

            if url in done_urls:
                continue

            if not os.path.exists(folder):
                os.makedirs(folder)

            print("%s - %s" % (count, filename))

            # Download the pdf
            path_name = folder + "/" + filename
            if path_name in path_set:
                path_name += "_1"

            response = session.get(url)
            with open(path_name + '.pdf', 'wb') as f_pdf:
                f_pdf.write(response.content)

            if (os.path.getsize(path_name + '.pdf') / 1024) < 20:
                print("error - file produced is too small")
                nb_attempts += 1

                if nb_attempts >= MAX_NB_ATTEMPTS:
                    print("Too many failed attempts, stopping.")
                    break

                time.sleep(randint(128, 512))
            else:
                nb_attempts = 0
                path_set.add(path_name)

                time.sleep(randint(2, 10))
                with open(PROCEEDINGS_PDF_DONE, 'a') as f_out:
                    f_out.write("%s\n" % url)

                count += 1
                if count % 243 == 0:
                    print("wait...")
                    time.sleep(randint(256, 1024))


if __name__ == '__main__':
    _main()
