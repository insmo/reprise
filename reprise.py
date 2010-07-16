#!/usr/bin/env python

from __future__ import with_statement

import os
import re
import sys
import time
import email
import shutil
import markdown

from docutils import core
from textwrap import dedent
from lxml.etree import tostring
from smartypants import smartyPants
from lxml.builder import ElementMaker
from datetime import datetime, timedelta
from jinja2 import DictLoader, Environment
from pygments.formatters import HtmlFormatter
from os.path import abspath, realpath, dirname, join
from optparse import OptionParser, make_option, OptionValueError, check_choice

TITLE = 'Journal'
URL = 'http://journal.uggedal.com'
STYLESHEET = 'style.css'

AUTHOR = {
    'name': 'Eivind Uggedal',
    'email': 'eivind@uggedal.com',
    'url': 'http://uggedal.com',
    'elsewhere': {
        '@uggedal': 'http://twitter.com/uggedal/',
        'Was it up?': 'http://wasitup.com/',
    }
}

ROOT = abspath(dirname(__file__))
DIRS = {
    'source': join(ROOT, 'entries'),
    'build': join(ROOT, 'build'),
    'public': join(ROOT, 'public'),
    'assets': join(ROOT, 'assets'),
    'templates': join(ROOT, 'templates'),
}

CONTEXT = {
    'author': AUTHOR,
    'body_title': "%s of %s" % (TITLE, AUTHOR['name']),
    'head_title': "%s of %s" % (TITLE, AUTHOR['name']),
    'analytics': 'UA-1857692-3',
    'stylesheet': STYLESHEET,
}

def handle_args():
    usage = "usage: %prog [options]"
    option_list = [
        make_option('-m', '--markup',
            choices=('reST', 'Markdown'),
            default='Markdown',
            help='Choices are `reST` and `Markdown`(default).',),
    ]
    parser = OptionParser(option_list=option_list, usage=usage)
    return parser.parse_args()
    
def _markup(content, options):
    if options.markup.lower() == 'rest':
        parts = core.publish_parts(source=content, writer_name='html')
        return parts['body_pre_docinfo']+parts['fragment']
    return markdown.markdown(content, ['codehilite', 'def_list'])

def read_and_parse_entries(options):
    files = sorted([join(DIRS['source'], f)
                    for f in os.listdir(DIRS['source'])], reverse=True)
    entries = []
    for file in files:
        match = META_REGEX.findall(file)
        if len(match):
            meta = match[0]
            with open(file, 'r') as fp:
                msg = email.message_from_file(fp)
                date = datetime(*[int(d) for d in meta[0:3]])
                entries.append({
                    'slug': slugify(meta[3]),
                    'title': meta[3].replace('.', ' '),
                    'tags': msg['Tags'].split(),
                    'date': {'iso8601': date.isoformat(),
                             'rfc3339': rfc3339(date),
                             'display': date.strftime('%Y-%m-%d'),},
                    'content_html': smartyPants(_markup(msg.get_payload(), options)),
                })
    return entries

def generate_index(entries, template):
    feed_url = "%s/index.atom" % URL
    html = template.render(dict(CONTEXT, **{'entries': entries,
                                            'feed_url': feed_url}))
    write_file(join(DIRS['build'], 'index.html'), html)
    atom = generate_atom(entries, feed_url)
    write_file(join(DIRS['build'], 'index.atom'), atom)

def generate_tag_indices(entries, template):
    for tag in set(sum([e['tags'] for e in entries], [])):
        tag_entries = [e for e in entries if tag in e['tags']]
        feed_url = "%s/tags/%s.atom" % (URL, tag)
        html = template.render(
            dict(CONTEXT, **{'entries': tag_entries,
                             'active_tag': tag,
                             'feed_url': feed_url,
                             'head_title': "%s: %s" % (CONTEXT['head_title'],
                                                       tag),}))
        write_file(join(DIRS['build'], 'tags', '%s.html' % tag), html)
        atom = generate_atom(tag_entries, feed_url)
        write_file(join(DIRS['build'], 'tags', '%s.atom' % tag), atom)

def generate_details(entries, template):
    for entry in entries:
        html = template.render(
            dict(CONTEXT, **{'entry': entry,
                             'head_title': "%s: %s" % (CONTEXT['head_title'],
                                                       entry['title'])}))
        write_file(join(DIRS['build'], '%s.html' % entry['slug']), html)

def generate_404(template):
        html = template.render(CONTEXT)
        write_file(join(DIRS['build'], '404.html'), html)

def generate_style(css):
    css2 = HtmlFormatter(style='trac').get_style_defs()
    write_file(join(DIRS['build'], STYLESHEET), ''.join([css, "\n\n", css2]))

def generate_atom(entries, feed_url):
    A = ElementMaker(namespace='http://www.w3.org/2005/Atom',
                     nsmap={None : "http://www.w3.org/2005/Atom"})
    entry_elements = []
    for entry in entries:
        entry_elements.append(A.entry(
            A.id(atom_id(entry=entry)),
            A.title(entry['title']),
            A.link(href="%s/%s" % (URL, entry['slug'])),
            A.updated(entry['date']['rfc3339']),
            A.content(entry['content_html'], type='html'),))
    return tostring(A.feed(A.author( A.name(AUTHOR['name']) ),
                           A.id(atom_id()),
                           A.title(TITLE),
                           A.link(href=URL),
                           A.link(href=feed_url, rel='self'),
                           A.updated(entries[0]['date']['rfc3339']),
                           *entry_elements), pretty_print=True)

def write_file(file_name, contents):
    with open(file_name, 'w') as fp:
        fp.write(contents.encode("utf-8"))

def read_file(file_name):
    with open(file_name, 'r') as fp:
        return fp.read()

def slugify(str):
    return re.sub(r'\s+', '-', re.sub(r'[^\w\s-]', '',
                                      str.replace('.', ' ').lower()))

def atom_id(entry=None):
    domain = re.sub(r'http://([^/]+).*', r'\1', URL)
    if entry:
        return "tag:%s,%s:/%s" % (domain, entry['date']['display'],
                                  entry['slug'])
    else:
        return "tag:%s,2009-03-04:/" % domain

def rfc3339(date):
    offset = -time.altzone if time.daylight else -time.timezone
    return (date + timedelta(seconds=offset)).strftime('%Y-%m-%dT%H:%M:%SZ')

def get_templates():
    src_files = (
        'base.html',
        'list.html',
        'detail.html',
        '_entry.html',
        '404.html',
        STYLESHEET,
    )
    templates = dict()
    for file in src_files:
        content = read_file(join(DIRS['templates'], file))
        templates[file] = dedent(content).strip()
    return templates

META_REGEX = re.compile(r"/(\d{4})\.(\d\d)\.(\d\d)\.(.+)")

if __name__ == "__main__":
    templates = get_templates()
    env = Environment(loader=DictLoader(templates))
    options, args = handle_args()
    all_entries = read_and_parse_entries(options)
    shutil.copytree(DIRS['assets'], DIRS['build'])
    generate_index(all_entries, env.get_template('list.html'))
    os.mkdir(join(DIRS['build'], 'tags'))
    generate_tag_indices(all_entries, env.get_template('list.html'))
    generate_details(all_entries, env.get_template('detail.html'))
    generate_404(env.get_template('404.html'))
    generate_style(templates[STYLESHEET])
    shutil.rmtree(DIRS['public'])
    shutil.move(DIRS['build'], DIRS['public'])
