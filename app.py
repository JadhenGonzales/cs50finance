import os

from cs50 import SQL
from flask import Flask, flash, redirect, render_template, request, session
from flask_session import Session
from werkzeug.security import check_password_hash, generate_password_hash

from helpers import apology, login_required, lookup, usd

# Configure application
app = Flask(__name__)

# Custom filter
app.jinja_env.filters["usd"] = usd

# Configure session to use filesystem (instead of signed cookies)
app.config["SESSION_PERMANENT"] = False
app.config["SESSION_TYPE"] = "filesystem"
Session(app)

# Configure CS50 Library to use SQLite database
db = SQL("sqlite:///finance.db")


@app.after_request
def after_request(response):
    """Ensure responses aren't cached"""
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    response.headers["Expires"] = 0
    response.headers["Pragma"] = "no-cache"
    return response


@app.route("/")
@login_required
def index():
    """Show portfolio of stocks"""

    # dictionary list of stocks, shares, and current values
    portfolio = db.execute("""SELECT symbol,
                                  SUM(shares) AS shares
                             FROM transactions
                            WHERE user_id = ? AND NOT symbol = "DEPOSIT"
                         GROUP BY symbol""", session.get("user_id"))

    # look up current prices for stocks
    sum = 0
    for stock in portfolio:
        if lookup(stock['symbol']) is not None:
            stock['value'] = float(lookup(stock['symbol'])['price'])
            stock['total'] = stock['shares'] * lookup(stock['symbol'])['price']
            sum += stock['total']

    # get user balance and total value
    current_balance = db.execute("SELECT cash FROM users WHERE id = ?", session.get("user_id"))[0]['cash']
    total = sum + current_balance

    return render_template("index2.html", portfolio=portfolio, cash=current_balance, total=total)

@app.route("/buy", methods=["GET", "POST"])
@login_required
def buy():
    """Buy shares of stock"""

    # User reached route via POST
    if request.method == "POST":

        quoted_stock = lookup(request.form.get("symbol"))

        # Return an error for invalid symbol
        if not quoted_stock or quoted_stock is None:
            return apology("code_error", 400)

        # Return an error for invalid number of shares
        try:
            shares = int(request.form.get("shares"))
        except ValueError:
            return apology("shares must be a positive integer")
        else:
            if shares < 0:
                return apology("shares must be a positive integer")

        value = shares * quoted_stock['price']
        current_balance = db.execute("SELECT cash FROM users WHERE id = ?", session.get("user_id"))[0]['cash']

        # Return an error if insufficient balance
        if value > current_balance:
            return apology("Insufficient Cash")

        # Insert into transactions table and deduct from cash
        db.execute("INSERT INTO transactions (user_id, symbol, shares, value) VALUES (?, ?, ?, ?)",
                   session.get("user_id"),
                   quoted_stock['symbol'],
                   shares,
                   - value)
        db.execute("UPDATE users SET cash = ? WHERE id = ?", current_balance - value, session.get("user_id"))

        return redirect("/")

    # User reached route via GET
    else:
        return render_template("buy.html")


@app.route("/history")
@login_required
def history():
    """Show history of transactions"""

    # Query transaction history and determine transaction type
    transactions = db.execute("SELECT symbol, shares, value, datetime FROM transactions WHERE user_id = ?", session.get("user_id"))
    for transaction in transactions:
        if transaction["shares"] >= 0:
            transaction['type'] = "BUY"
            transaction['value'] = - transaction['value']
        else:
            transaction['type'] = "SELL"
            transaction['shares'] = - transaction['shares']

    return render_template("history.html", transactions=transactions)


@app.route("/login", methods=["GET", "POST"])
def login():
    """Log user in"""

    # Forget any user_id
    session.clear()

    # User reached route via POST (as by submitting a form via POST)
    if request.method == "POST":

        # Ensure username was submitted
        if not request.form.get("username"):
            return apology("must provide username", 403)

        # Ensure password was submitted
        elif not request.form.get("password"):
            return apology("must provide password", 403)

        # Query database for username
        rows = db.execute("SELECT * FROM users WHERE username = ?", request.form.get("username"))

        # Ensure username exists and password is correct
        if len(rows) != 1 or not check_password_hash(rows[0]["hash"], request.form.get("password")):
            return apology("invalid username and/or password", 403)

        # Remember which user has logged in
        session["user_id"] = rows[0]["id"]

        # Redirect user to home page
        return redirect("/")

    # User reached route via GET (as by clicking a link or via redirect)
    else:
        return render_template("login.html")


@app.route("/logout")
def logout():
    """Log user out"""

    # Forget any user_id
    session.clear()

    # Redirect user to login form
    return redirect("/")


@app.route("/options", methods=["GET", "POST"])
@login_required
def options():
    """Show multiple options"""

    # User reached route via POST
    if request.method == "POST":
        current_balance = db.execute("SELECT cash FROM users WHERE id = ?", session.get("user_id"))[0]['cash']

        db.execute("INSERT INTO transactions (user_id, symbol, shares, value) VALUES (?, ?, ?, ?)",
                   session.get("user_id"),
                   "DEPOSIT",
                   0,
                   int(request.form.get("amount")))
        db.execute("UPDATE users SET cash = ? WHERE id = ?", current_balance + int(request.form.get("amount")), session.get("user_id"))

        return redirect("/")

    # User reached route via GET
    else:
        return render_template("options.html")


@app.route("/quote", methods=["GET", "POST"])
@login_required
def quote():
    """Get stock quote."""

    # User reached route via POST
    if request.method == "POST":
        quoted_stock = lookup(request.form.get("symbol"))

        # Return an error for invalid symbol
        if not quoted_stock:
            return apology("code_error.html", 400)

        return render_template("quoted.html", quoted_stock=quoted_stock)

    # User reached route via GET
    else:
        return render_template("quote.html")


@app.route("/register", methods=["GET", "POST"])
def register():
    """Register user"""

    # Forget any user_id
    session.clear()

    # User reached route via POST
    if request.method == "POST":

        # Ensure username was submitted
        if not request.form.get("username"):
            return apology("must provide username", 400)

        # Ensure username is unique
        username = db.execute("SELECT username FROM users WHERE username = ?", request.form.get("username"))
        if username:
            return apology("username already exists")

        # Ensure password was submitted
        elif not request.form.get("password"):
            return apology("must provide password", 400)

        # Ensure confirmation is same as password was submitted
        elif request.form.get("confirmation") != request.form.get("password"):
            return apology("Both passwords must match", 400)

        # Insert into users
        db.execute("INSERT INTO users (username, hash) VALUES (?, ?)", request.form.get("username"), generate_password_hash(request.form.get("password")))
        return redirect("/login")

    # User reached route via GET
    else:
        return render_template("register.html")


@app.route("/sell", methods=["GET", "POST"])
@login_required
def sell():
    """Sell shares of stock"""

    # User reached route via POST
    if request.method == "POST":

        quoted_stock = lookup(request.form.get("symbol"))

        # Return an error for invalid symbol
        if not quoted_stock:
            return apology("code_error", 400)

        # Return an error for invalid number of shares
        try:
            shares = int(request.form.get("shares"))
        except ValueError:
            return apology("shares must be a positive integer")
        else:
            if shares < 0:
                return apology("shares must be a positive integer")

        # Return an error if insufficient balance
        current = db.execute("SELECT SUM(shares) AS shares FROM transactions WHERE user_id = ? AND symbol = ?", session.get("user_id"), request.form.get("symbol"))
        if shares > current[0]['shares']:
            return apology("Insufficient Shares")

        # Insert into transactions table and deduct from cash
        current_balance = db.execute("SELECT cash FROM users WHERE id = ?", session.get("user_id"))[0]['cash']
        value = shares * quoted_stock['price']

        db.execute("INSERT INTO transactions (user_id, symbol, shares, value) VALUES (?, ?, ?, ?)",
                   session.get("user_id"),
                   quoted_stock['symbol'],
                   - shares,
                   value)
        db.execute("UPDATE users SET cash = ? WHERE id = ?", current_balance + value, session.get("user_id"))

        return redirect("/")

    # User reached route via GET
    else:
        portfolio = db.execute("""SELECT symbol
                            FROM transactions
                        WHERE user_id = ? AND NOT symbol = "DEPOSIT"
                        GROUP BY symbol""", session.get("user_id"))

        return render_template("sell.html", portfolio=portfolio)
