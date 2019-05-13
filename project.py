from flask import (
    Flask, render_template, request, redirect, jsonify, url_for, flash)
from sqlalchemy import create_engine, asc
from sqlalchemy.orm import sessionmaker, scoped_session
from database_setup import Base, Restaurant, MenuItem, User
from flask import session as login_session
import random
import string
from oauth2client.client import flow_from_clientsecrets
from oauth2client.client import FlowExchangeError
import httplib2
import json
from flask import make_response
import requests

app = Flask(__name__)

APPLICATION_NAME = "Restaurant Menu Application"

# Connect to Database and create database session
engine = create_engine(
    'postgresql://catalog:123@localhost/catalog')
Base.metadata.bind = engine
session = scoped_session(sessionmaker(bind=engine))


# Login function and create anti-forgery state token
@app.route('/login/')
def showLogin():
    """
    Create a state token for anti-forgery and run the login html page.
    """
    state = ''.join(random.choice(string.ascii_uppercase + string.digits)
                    for x in xrange(32))
    login_session['state'] = state
    return render_template('login.html', STATE=state)


# User Helper Functions
def createUser(login_session):
    """
    Create a user in the database, if the user logged in for the first time.
    """
    newUser = User(name=login_session['username'], email=login_session[
                   'email'], picture=login_session['picture'])
    session.add(newUser)
    session.commit()
    user = session.query(User).filter_by(email=login_session['email']).one()
    return user.id


def getUserInfo(user_id):
    """
    Get an user info in the database.
    """
    user = session.query(User).filter_by(id=user_id).one()
    return user


def getUserID(email):
    """
    Search for an id info of an user in the database.
    """
    try:
        user = session.query(User).filter_by(email=email).one()
        return user.id
    except:  # noqa
        return None


# Functions to get user info of facebook account and register
@app.route('/fbconnect', methods=['POST'])
def fbconnect():
    """
    Get data from Facebook Sign In API and places it
    inside a session variable.
    """

    if request.args.get('state') != login_session['state']:
        response = make_response(json.dumps('Invalid state parameter.'), 401)
        response.headers['Content-Type'] = 'application/json'
        return response
    access_token = request.data
    print "access token received %s " % access_token

    app_id = json.loads(open('fb_client_secrets.json', 'r').read())[
        'web']['app_id']
    app_secret = json.loads(
        open('fb_client_secrets.json', 'r').read())['web']['app_secret']
    url = 'https://graph.facebook.com/oauth/access_token?grant_type=fb_exchange_token&client_id=%s&client_secret=%s&fb_exchange_token=%s' % (app_id, app_secret, access_token)  # noqa
    h = httplib2.Http()
    result = h.request(url, 'GET')[1]

    # Use token to get user info from API
    userinfo_url = "https://graph.facebook.com/v2.8/me"
    '''
        Due to the formatting for the result from the server token exchange
        we have to split the token first on commas and select the first
        index which gives us the key : value for the server access token
        then we split it on colons to pull out the actual token value
        and replace the remaining quotes with nothing so that it can be
        used directly in the graph api calls
    '''
    token = result.split(',')[0].split(':')[1].replace('"', '')

    url = 'https://graph.facebook.com/v2.8/me?access_token=%s&fields=name,id,email' % token  # noqa
    h = httplib2.Http()
    result = h.request(url, 'GET')[1]

    data = json.loads(result)
    login_session['provider'] = 'facebook'
    login_session['username'] = data["name"]
    login_session['email'] = data["email"]
    login_session['facebook_id'] = data["id"]

    # The token must be stored in the login_session in order to properly logout
    login_session['access_token'] = token

    # Get user picture
    url = 'https://graph.facebook.com/v2.8/me/picture?access_token=%s&redirect=0&height=200&width=200' % token  # noqa
    h = httplib2.Http()
    result = h.request(url, 'GET')[1]
    data = json.loads(result)

    login_session['picture'] = data["data"]["url"]

    # see if user exists
    user_id = getUserID(login_session['email'])
    if not user_id:
        user_id = createUser(login_session)
    login_session['user_id'] = user_id

    output = ''
    output += '<h1>Welcome, '
    output += login_session['username']

    output += '!</h1>'
    output += '<img src="'
    output += login_session['picture']
    output += '  "style = "width: 300px; height: 300px;border-radius: 150px;-webkit-border-radius: 150px;-moz-border-radius: 150px;"> '  # noqa

    flash("Now logged in as %s" % login_session['username'])
    return output


@app.route('/fbdisconnect')
def fbdisconnect():
    """
    Get the data of the login session and disconnect the user.
    """
    facebook_id = login_session['facebook_id']
    # The access token must me included to successfully logout
    access_token = login_session['access_token']
    url = 'https://graph.facebook.com/%s/permissions?access_token=%s' % (
        facebook_id, access_token)
    h = httplib2.Http()
    result = h.request(url, 'GET')[0]
    return "you have been logged out"


@app.route('/disconnect')
def disconnect():
    """
    Verify the data of the login session, disconnect the user,
    delete the data of the session by calling fbdisconnect function
    and return to the main html page.
    """
    if 'provider' in login_session:
        if login_session['provider'] == 'facebook':
            fbdisconnect()
            del login_session['facebook_id']
            del login_session['username']
            del login_session['email']
            del login_session['picture']
            del login_session['user_id']
            del login_session['provider']
            flash("You have successfully been logged out.")
            return redirect(url_for('showRestaurants'))
    else:
        flash("You were not logged in")
        return redirect(url_for('showRestaurants'))


# JSON APIs to view Restaurant Information
@app.route('/restaurant/<int:restaurant_id>/menu/JSON')
def restaurantMenuJSON(restaurant_id):
    """
    Get all the menus of the restaurants in the database and show its json
    objects.
    """
    restaurant = session.query(Restaurant).filter_by(id=restaurant_id).one()
    items = session.query(MenuItem).filter_by(
        restaurant_id=restaurant_id).all()
    return jsonify(MenuItems=[i.serialize for i in items])


@app.route('/restaurant/<int:restaurant_id>/menu/<int:menu_id>/JSON')
def menuItemJSON(restaurant_id, menu_id):
    """
    Get all the menus items of the restaurants in the database and show
    its json objects.
    """
    Menu_Item = session.query(MenuItem).filter_by(id=menu_id).one()
    return jsonify(Menu_Item=Menu_Item.serialize)


@app.route('/restaurant/JSON')
def restaurantsJSON():
    """
    Get all the restaurants that are in the database and show its json
    objects.
    """
    restaurants = session.query(Restaurant).all()
    return jsonify(restaurants=[r.serialize for r in restaurants])
# End of JSON APIs


# Show all restaurants
@app.route('/')
@app.route('/restaurant/')
def showRestaurants():
    """
    Get all the restaurants that are in the database and verify if the
    user has a register to show the right html page.
    """
    restaurants = session.query(Restaurant).order_by(asc(Restaurant.name))
    if 'username' not in login_session:
        return render_template(
            'publicrestaurants.html', restaurants=restaurants)
    else:
        return render_template('restaurants.html', restaurants=restaurants)


# Create a new restaurant
@app.route('/restaurant/new/', methods=['GET', 'POST'])
def newRestaurant():
    """
    Verify if the user has a register. If the user has a register, allows it
    to create a new restaurant.
    """
    if 'username' not in login_session:
        return redirect(url_for('showLogin'))
    if request.method == 'POST':
        newRestaurant = Restaurant(
            name=request.form['name'], user_id=login_session['user_id'])
        session.add(newRestaurant)
        session.commit()
        flash('New Restaurant %s Successfully Created' % newRestaurant.name)
        return redirect(url_for('showRestaurants'))
    else:
        return render_template('newRestaurant.html')


# Edit a restaurant
@app.route('/restaurant/<int:restaurant_id>/edit/', methods=['GET', 'POST'])
def editRestaurant(restaurant_id):
    """
    Verify if the user has a register. If the user has a register, allows it
    to edit the name of a restaurant.
    """
    editedRestaurant = session.query(
        Restaurant).filter_by(id=restaurant_id).one()
    if 'username' not in login_session:
        return redirect(url_for('showLogin'))
    if editedRestaurant.user_id != login_session['user_id']:
        return ("<script>function myFunction() "
                "{alert('You are not authorized to edit this restaurant. "
                "Please create your own restaurant in order to edit.');}"
                "</script><body onload='myFunction()'>")
    if request.method == 'POST':
        if request.form['name']:
            editedRestaurant.name = request.form['name']
            flash('Restaurant Successfully Edited %s' % editedRestaurant.name)
            return redirect(url_for('showRestaurants'))
    else:
        return render_template(
            'editRestaurant.html', restaurant=editedRestaurant)


# Delete a restaurant
@app.route('/restaurant/<int:restaurant_id>/delete/', methods=['GET', 'POST'])
def deleteRestaurant(restaurant_id):
    """
    Verify if the user has a register. If the user has a register, allows it
    to delete a restaurant.
    """
    restaurantToDelete = session.query(
        Restaurant).filter_by(id=restaurant_id).one()
    if 'username' not in login_session:
        return redirect(url_for('showLogin'))
    if restaurantToDelete.user_id != login_session['user_id']:
        return ("<script>function myFunction() "
                "{alert('You are not authorized to delete this restaurant. "
                "Please create your own restaurant in order to delete.');}"
                "</script><body onload='myFunction()'>")
    if request.method == 'POST':
        session.delete(restaurantToDelete)
        session.commit()
        flash('%s Successfully Deleted' % restaurantToDelete.name)
        return redirect(url_for(
            'showRestaurants', restaurant_id=restaurant_id))
    else:
        return render_template(
            'deleteRestaurant.html', restaurant=restaurantToDelete)


# Show a restaurant menu
@app.route('/restaurant/<int:restaurant_id>/')
@app.route('/restaurant/<int:restaurant_id>/menu/')
def showMenu(restaurant_id):
    """
    Get the menu of a restaurant in the database and verify if the
    user has a register to show the right html page.
    """
    restaurant = session.query(Restaurant).filter_by(id=restaurant_id).one()
    creator = getUserInfo(restaurant.user_id)
    items = session.query(MenuItem).filter_by(
        restaurant_id=restaurant_id).all()
    if (
        'username'
        not in login_session or
        (
            creator.id != login_session['user_id']
            )
    ):
        return render_template(
            'publicmenu.html', items=items, restaurant=restaurant,
            creator=creator)
    else:
        return render_template(
            'menu.html', items=items, restaurant=restaurant, creator=creator)


# Create a new menu item
@app.route(
    '/restaurant/<int:restaurant_id>/menu/new/',
    methods=['GET', 'POST'])
def newMenuItem(restaurant_id):
    """
    Verify if the user has a register. If the user has a register, allows it
    to create a new menu item.
    """
    if 'username' not in login_session:
        return redirect(url_for('showLogin'))
    restaurant = session.query(Restaurant).filter_by(id=restaurant_id).one()
    if login_session['user_id'] != restaurant.user_id:
        return ("<script>function myFunction() "
                "{alert('You are not authorized to add menu items to this "
                "restaurant. Please create your own restaurant in order to "
                "add items.');}</script><body onload='myFunction()'>")
    if request.method == 'POST':
        newItem = MenuItem(
            name=request.form['name'], description=request.form['description'],
            price=request.form['price'], course=request.form['course'],
            restaurant_id=restaurant_id, user_id=restaurant.user_id)
        session.add(newItem)
        session.commit()
        flash('New Menu %s Item Successfully Created' % (newItem.name))
        return redirect(url_for('showMenu', restaurant_id=restaurant_id))
    else:
        return render_template('newmenuitem.html', restaurant_id=restaurant_id)


# Edit a menu item
@app.route(
    '/restaurant/<int:restaurant_id>/menu/<int:menu_id>/edit',
    methods=['GET', 'POST'])
def editMenuItem(restaurant_id, menu_id):
    """
    Verify if the user has a register. If the user has a register, allows it
    to edit a menu item.
    """
    if 'username' not in login_session:
        return redirect(url_for('showLogin'))
    editedItem = session.query(MenuItem).filter_by(id=menu_id).one()
    restaurant = session.query(Restaurant).filter_by(id=restaurant_id).one()
    if login_session['user_id'] != restaurant.user_id:
        return ("<script>function myFunction() "
                "{alert('You are not authorized to edit menu items to this "
                "restaurant. Please create your own restaurant in order to "
                "edit items.');}</script><body onload='myFunction()'>")
    if request.method == 'POST':
        if request.form['name']:
            editedItem.name = request.form['name']
        if request.form['description']:
            editedItem.description = request.form['description']
        if request.form['price']:
            editedItem.price = request.form['price']
        if request.form['course']:
            editedItem.course = request.form['course']
        session.add(editedItem)
        session.commit()
        flash('Menu Item Successfully Edited')
        return redirect(url_for('showMenu', restaurant_id=restaurant_id))
    else:
        return render_template(
            'editmenuitem.html', restaurant_id=restaurant_id,
            menu_id=menu_id, item=editedItem)


# Delete a menu item
@app.route(
    '/restaurant/<int:restaurant_id>/menu/<int:menu_id>/delete',
    methods=['GET', 'POST'])
def deleteMenuItem(restaurant_id, menu_id):
    """
    Verify if the user has a register. If the user has a register, allows it
    to delete menu item.
    """
    restaurant = session.query(Restaurant).filter_by(id=restaurant_id).one()
    itemToDelete = session.query(MenuItem).filter_by(id=menu_id).one()
    if 'username' not in login_session:
        return redirect(url_for('showLogin'))
    if login_session['user_id'] != restaurant.user_id:
        return ("<script>function myFunction() "
                "{alert('You are not authorized to delete menu items to "
                "this restaurant. Please create your own restaurant in order "
                "to delete items.');}</script><body onload='myFunction()'>")
    if request.method == 'POST':
        session.delete(itemToDelete)
        session.commit()
        flash('Menu Item Successfully Deleted')
        return redirect(url_for('showMenu', restaurant_id=restaurant_id))
    else:
        return render_template('deletemenuitem.html', item=itemToDelete)


if __name__ == '__main__':
    app.secret_key = 'new_super_secret_key'
    app.debug = True
    app.run()
