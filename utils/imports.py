from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove
from telegram.ext import CommandHandler, Application, CallbackContext, MessageHandler, CallbackQueryHandler, filters
import logging, sqlite3, re, pytz, json, os, zipfile
from datetime import timedelta, time, datetime, date
# ...інші імпорти...