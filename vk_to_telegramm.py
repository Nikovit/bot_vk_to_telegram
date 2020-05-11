# -*- coding: utf-8 -*-

import os
import sys
import vk_api
import telebot
import configparser
import logging
from telebot.types import InputMediaPhoto
import time
import getopt,sys

try:
    opts, args = getopt.getopt(sys.argv[1:], "hc:", ["help", "config="])
except getopt.GetoptError as err:
    # print help information and exit:
    print(str(err))  # will print something like "option -a not recognized"
    #usage()
    sys.exit(2)

CONFIG_FILE="settings.ini"

for o, a in opts:
    if o in ("-c", "--config"):
        CONFIG_FILE = a
    else:
        assert False, "unhandled option"

# Считываем настройки
config_path = os.path.join(sys.path[0], CONFIG_FILE)
config = configparser.ConfigParser()
config.read(config_path)
LOGIN = config.get('VK', 'LOGIN')
PASSWORD = config.get('VK', 'PASSWORD')
DOMAIN = config.get('VK', 'DOMAIN')
COUNT = config.get('VK', 'COUNT')
VK_TOKEN = config.get('VK', 'TOKEN', fallback=None)
BOT_TOKEN = config.get('Telegram', 'BOT_TOKEN')
CHANNEL = config.get('Telegram', 'CHANNEL')
INCLUDE_LINK = config.getboolean('Settings', 'INCLUDE_LINK')
PREVIEW_LINK = config.getboolean('Settings', 'PREVIEW_LINK')

# Символы, на которых можно разбить сообщение
message_breakers = [':', ' ', '\n']
max_message_length = 4091
max_capt_length = 1024

delim = '\n***********************************'
rep_delim = '\n------конец репоста-----------------'
# Инициализируем телеграмм бота
bot = telebot.TeleBot(BOT_TOKEN)


# Получаем данные из vk.com
def get_data(domain_vk, count_vk):
    global LOGIN
    global PASSWORD
    global VK_TOKEN
    global config
    global config_path

    if VK_TOKEN is not None:
        vk_session = vk_api.VkApi(LOGIN, PASSWORD, VK_TOKEN)
        vk_session.auth(token_only=True)
    else:
        vk_session = vk_api.VkApi(LOGIN, PASSWORD)
        vk_session.auth()

    new_token = vk_session.token['access_token']
    if VK_TOKEN != new_token:
        VK_TOKEN = new_token
        config.set('VK', 'TOKEN', new_token)
        with open(config_path, "w") as config_file:
            config.write(config_file)

    vk = vk_session.get_api()
    # Используем метод wall.get из документации по API vk.com
    response = vk.wall.get(domain=domain_vk, count=count_vk)
    return response


# Проверяем данные по условиям перед отправкой
def check_posts_vk():
    global DOMAIN
    global COUNT
    global INCLUDE_LINK
    global bot
    global config
    global config_path

    response = get_data(DOMAIN, COUNT)
    response = reversed(response['items'])

    for post in response:

        # Читаем последний извесный id из файла
        id = config.get('Settings', 'LAST_ID')

        # Сравниваем id, пропускаем уже опубликованные
        if int(post['id']) <= int(id):
            continue

        print('------------------------------------------------------------------------------------------------')
        print(post)

        # Текст
        text = post['text']

        # Проверяем есть ли что то прикрепленное к посту
        images = []
        links = []
        attachments = []
        if 'attachments' in post:
            attach = post['attachments']
            for add in attach:
                if add['type'] == 'photo':
                    img = add['photo']
                    images.append(img)
                elif add['type'] == 'audio':
                    # Все аудиозаписи заблокированы везде, кроме оффицальных приложений
                    continue
                elif add['type'] == 'video':
                    video = add['video']
                    if 'player' in video:
                        links.append(video['player'])
                else:
                    for (key, value) in add.items():
                        if key != 'type' and 'url' in value:
                            attachments.append(value['url'])

        if INCLUDE_LINK:
            post_url = "https://vk.com/" + DOMAIN + "?w=wall" + \
                str(post['owner_id']) + '_' + str(post['id'])
            links.insert(0, post_url)
        text = '\n'.join([text] + links)
        data = {'type':'main', 'images': images, 'text': text}
        post_data(**data)


        # Проверяем есть ли репост другой записи
        att_imgs = []
        lnk_text = []
        if 'copy_history' in post:
            copy_history = post['copy_history']
            copy_history = copy_history[0]
            print('--copy_history--')
            print(copy_history)

            # Проверяем есть ли у репоста прикрепленное сообщение
            if 'attachments' in copy_history:
                copy_add = copy_history['attachments']
                copy_add = copy_add[0]

                # Если это картинки
                if copy_add['type'] == 'photo':
                    attach = copy_history['attachments']
                    for img in attach:
                        if 'photo' in img:
                            image = img['photo']
                            att_imgs.append(image)

                # Если это ссылка
                if copy_add['type'] == 'link':
                    link = copy_add['link']
                    lnk_text.append(link['title'])
                    lnk_text.append(link['url'])
                    #TODO: need refactor this -when we have multiple images and this in same time
                    img = link['photo']
                    #TBD: need to figure out this
                    #send_posts_img(img)
                    att_imgs.append(img)

            text = '\n'.join([copy_history['text']] + lnk_text)
            data = {'type':'repost', 'images': att_imgs, 'text': text}
            post_data(**data)

        # Записываем id в файл
        config.set('Settings', 'LAST_ID', str(post['id']))
        with open(config_path, "w") as config_file:
            config.write(config_file)


# Отправляем посты в телеграмм


def post_data(**data):
    # data - {'type':type,'images':images, 'text':text}
    type = data.get('type', 'main')
    images = data.get('images',[])
    text = data.get('text','')
    body = {'type': type, 'pic': False, 'body': text }
        if len(images) > 1:
            image_urls = list(map(lambda img: max(
                img["sizes"], key=lambda size: size["type"])["url"], images))
            print(image_urls)
            bot.send_media_group(CHANNEL, map(
                lambda url: InputMediaPhoto(url), image_urls))
            send_posts_text(**body)
        elif len(images) == 1:
            body['pic'] = True
            send_posts_img(**body)
        else:
            send_posts_text(**body)

# Текст
def send_posts_text( **data):
    global CHANNEL
    global PREVIEW_LINK
    global bot

    type = data.get('type', 'main')
    text = data.get('text')

    # В телеграмме есть ограничения на длину одного сообщения в 4091 символ, разбиваем длинные сообщения на части
    for msg in split(**data):
        bot.send_message(CHANNEL, msg, disable_web_page_preview=not PREVIEW_LINK)

def set_delim(type):
    global delim
    global rep_delim

    if type == 'main':
        return delim
    elif type == 'repost':
        return rep_delim
    else:
        return None


def split(**message):
    # message format: {'type': 'main', 'pic':True, 'body': 'текст сообщения'}
    # message types: main - 'common text for messages and caption', repost - 'text or caption for repost'
    # message def: 'pic' True or False, if image exists

    global message_breakers
    global max_message_length
    global max_capt_length

    type = message.get('type', 'main')
    text = message.get('body')

    if message.get('pic', False):
        max_length = max_capt_length
    else:
        max_length = max_message_length

    delim = set_delim(type)
    text = text + delim

    if len(text) >= max_length:
        last_index = max(
            map(lambda separator: text.rfind(separator, 0, max_message_length), message_breakers))
        good_part = text[:last_index]
        message['body'] = text[last_index + 1:]
        return [good_part] + split(**message)
    else:
        return [text]


# Изображения
def send_posts_img(**object):
    global bot

    img = object.get('images', [])[0]
    # Находим картинку с максимальным качеством
    url = max(img["sizes"], key=lambda size: size["type"])["url"]

    caption = split(**object)[0]
    bot.send_photo(CHANNEL, url, caption)


if __name__ == '__main__':
    check_posts_vk()
