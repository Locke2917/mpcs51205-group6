
import os
import sys
import datetime
import traceback
from flask import Flask, request, session, g, redirect, url_for, abort, \
     render_template, flash, escape, json, jsonify, Response, Blueprint
import requests
from . import user_client as users
from . import auction_client as auctions
from . import authentication_client as auth
from . import item_client as items

bp = Blueprint('routes', __name__, url_prefix='/')


def check_login():
    if not session.get('username'): return False
    return auth.check_login(session.get('username'))

#*********************************************************************
# Home, display list of auctions
#*********************************************************************
@bp.route('/', methods=['GET'])
@bp.route('/auction_list', methods=['GET'])
@bp.route('/auction_list/<sort>', methods=['GET', 'POST'])
def auction_list(sort='start_time'):

    print(request.form)

    if not check_login():
        return redirect( url_for('routes.login') )

    auction_list = auctions.get_all_auctions()
    categories = items.get_all_categories()
    for auction in auction_list:
        auction['item'] = items.get_item_details(auction['item'])['result']
        auction['current_bid'] = auctions.get_highest_bid(auction['id'])['max_bid']
        for category in categories:
            if category['id'] == auction['item']['category']:
                auction['item']['category_details'] = category
                break
            auction['item']['category_details'] = {
                'id': None,
                'name': None
            }

    if request.form.get('search_term'):
        search_term = request.form.get('search_term')
    else:
        search_term = False


    auction_list = sorted(auction_list, key = lambda i: i[sort])

    print('CHIP ', search_term)

    return_list = []
    for auction in auction_list:
        if search_term:
            print(auction['item']['category_details']['name'], ' ' )
            if auction['item']['category_details']['name'] and search_term.lower() in auction['item']['category_details']['name'].lower():
                return_list.append(auction)
            elif auction['item']['name'] and search_term.lower() in auction['item']['name'].lower():
                return_list.append(auction)
            elif auction['item']['description'] and search_term.lower() in auction['item']['description'].lower():
                return_list.append(auction)
            elif auction['name'] and search_term.lower() in auction['name'].lower():
                return_list.append(auction)
        else:
            return_list.append(auction)

    template = render_template('auction_list.html', 
        auction_list=return_list,
        sort=sort
    )
    
    return template

@bp.route('/auction/create', methods=['GET', 'POST'])
def create_auction():
    error = None
    auction=None
    item=None

    print(request.form)

    categories = items.get_all_categories()

    if request.method == 'POST':
        try:
            start_datetime = datetime.datetime.combine(datetime.datetime.strptime(request.form.get('start_date'), '%Y-%m-%d'), datetime.datetime.strptime(request.form.get('start_time'), '%H:%M').time()) 
            end_datetime = start_datetime + datetime.timedelta(hours=int(request.form['duration']))
        except Exception as e:
            return render_template('create_auction.html', auction=auction, item=item, categories=categories, error='Invalid Start Time: %s' % str(e))

        if request.form['new_category'] and request.form['new_category'] != '':
            category_response = items.create_category(request.form['new_category'])
            category = category_response['result']['id']
        else:
            raise ValueError('hmm')
            category = request.form['category']
            
        item_data = {
            'name': request.form['item_name'],
            'description': request.form['item_description'],
            'name': request.form['item_name'],
            'category': category
        }

        item_result = items.create_item(item_data)

        auction_data = {
            'name': request.form['auction_name'],
            'buy_now_price': request.form['buy_now_price'],
            'start_bid_price': request.form['start_bid_price'],
            'inc_bid_price': request.form['inc_bid_price'],
            'start_time': start_datetime,
            'end_time': end_datetime,
            'creator': session.get('username'),
            'item': item_result['result']['id']
        }

        auction_result = auctions.create_auction(auction_data)

        if auction_result.get('result'):
            return get_auction_details(auction_id=auction_result['content']['id'])
        else:
            error = auction_result.get('content')

    template = render_template('create_auction.html', auction=auction, item=item, categories=categories, error=error)

    return template

@bp.route('/auction/update/<auction_id>', methods=['GET', 'POST'])
def update_auction(auction_id):

    return redirect(url_for('routes.get_auction_details', auction_id=auction_id))

@bp.route('/item/update/<item_id>/<auction_id>', methods=['GET', 'POST'])
def update_item(item_id, auction_id):

    return redirect(url_for('routes.get_auction_details', auction_id=auction_id))

@bp.route('/auction/bid/<auction_id>', methods=['GET', 'POST'])
def place_bid(auction_id):
    
    try:
        amount = int(request.form.get('bid_amount'))
    except Exception as e:
        return get_auction_details(auction_id=auction_id, bid_error="Invalid Bid Format")

    response = auctions.place_bid(auction_id, session.get('username'), amount, datetime.datetime.now())

    print(response)

    if response['result'] == False:
        bid_error = response['content']
    else:
        bid_error = None

    return get_auction_details(auction_id=auction_id, bid_error=bid_error)

@bp.route('/auction/buy-now/<auction_id>', methods=['GET', 'POST'])
def buy_now():
    return get_auction_details(auction_id=auction_id)

@bp.route('/auction/end-auction/<auction_id>', methods=['GET', 'POST'])
def end_auction(auction_id):

    data = {
        'status': 'ended',
        'end_time': datetime.datetime.now()
    }

    auctions.update_auction(auction_id, data)

    return get_auction_details(auction_id=auction_id)

@bp.route('/auction/add-to-watchlist/<auction_id>', methods=['GET', 'POST'])
def add_to_watchlist(auction_id):

    response = users.add_to_watchlist(session.get('username', auction_id))

    return get_auction_details(auction_id=auction_id)

@bp.route('/auction/flag-item/<item_id>/<auction_id>', methods=['GET', 'POST'])
def flag_item(item_id, auction_id):

    response = items.flag_item(item_id)

    print(response)

    return get_auction_details(auction_id=auction_id)

@bp.route('/auction/<auction_id>', methods=['GET'])
def get_auction_details(auction_id, bid_error=None):

    auction_details = auctions.get_auction_details(auction_id)
    item_details = items.get_item_details(auction_details['result']['item'])
    categories = items.get_all_categories()

    for category in categories:
        if category['id'] == item_details['result']['category']:
            item_details['result']['category_details'] = category
            break
        item_details['result']['category_details'] = {
            'id': None,
            'name': None
        }
    highest_bid = auctions.get_highest_bid(auction_id)

    try:
        next_bid = int(highest_bid['max_bid'] + auction_details['result']['inc_bid_price'])
    except Exception as e:
        print(e)
        next_bid = 0

    template = render_template('auction_details.html', 
        auction=auction_details.get('result'),
        item=item_details.get('result'),
        categories=categories,
        highest_bid=highest_bid['max_bid'],
        bid_error=bid_error,
        next_bid=next_bid
    )
    
    return template

@bp.route('/login', methods=['GET', 'POST'])
def login():

    error = None

    if request.method == 'POST':
        result = auth.login(request.form['username'], request.form['password'])
        if result.get('result') == True:
            session['username'] = request.form['username']
            session['is_admin'] = result['content']
            return redirect(url_for('routes.auction_list'))
        else:
            error = result.get('content')

    template = render_template('login.html', error=error)

    return template

@bp.route('/logout',methods=['POST', 'GET'])
def logout():

     auth.logout(session.get('username'))

     session['username'] = None

     return redirect(url_for('routes.login'))

@bp.route('/signup', methods=['GET', 'POST'])
def signup():
    error = None

    if request.method == 'POST':
        if request.form['is_admin'] == "TRUE": is_admin = True
        else: is_admin = False


        user_result = users.create_user(request.form)
        credential_result = auth.create_credentials(request.form['username'], request.form['password'], is_admin)
        if user_result.get('result') and credential_result.get('result') == True:
            result = auth.login(request.form['username'], request.form['password'])
            session['username'] = request.form['username']
            session['is_admin'] = is_admin
            return redirect(url_for('routes.auction_list'))
        else:
            if user_result.get('result')  == False:
                error = user_result.get('content')
            if credential_result.get('result')  == False:
                error = credential_result.get('content')

    template = render_template('signup.html', error=error)

    return template


@bp.route('/user-updates/<username>',methods=['POST', 'GET'])
def user_update(username):

    user_details = users.update_user(username, request.form)

    return user_details(username=username)
    
@bp.route('/user/<username>',methods=['POST', 'GET'])
def user_details(username):

    if username != session.get('username') and not session.get('is_admin'):
        return "<h1>You are not this user and you are not an admin</h1>"

    user_details = users.get_user_details(username)

    template = render_template('user_details.html', 
        user_details=user_details.get('content')
    )
    
    return template


@bp.route('/admin', methods=['GET', 'POST'])
def admin():
    if request.method == 'POST':
        categories = request.form

    flags = items.get_all_flags()
    categories = items.get_all_categories()
    print(flags)
    template = render_template('admin.html', categories=categories, flags=flags)

    return template

@bp.route('/admin/category-update', methods=['GET', 'POST'])
def category_update():

    print(request.form)

    for key in request.form:
        if key == 'new_category':
            if request.form[key] and request.form[key] != "":
                items.create_category(request.form[key])
        else: 
            items.update_category(key, request.form[key])

    return admin()