from utils import helper
import os
from .models import User

def main():
    user = User('test')
    helper.process(user)
