import json, os, django
from confluent_kafka import Consumer
import traceback

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "core.settings")
django.setup()

from django.apps import apps
from django.db.models import Q

Cart = apps.get_model('cart', 'Cart')
CartItem = apps.get_model('cart', 'CartItem')

consumer1 = Consumer({
    'bootstrap.servers': os.environ.get('KAFKA_BOOTSTRAP_SERVER'),
    'security.protocol': os.environ.get('KAFKA_SECURITY_PROTOCOL'),
    'sasl.username': os.environ.get('KAFKA_USERNAME'),
    'sasl.password': os.environ.get('KAFKA_PASSWORD'),
    'sasl.mechanism': 'PLAIN',
    'group.id': os.environ.get('KAFKA_GROUP'),
    'auto.offset.reset': 'earliest'
})
consumer1.subscribe([os.environ.get('KAFKA_TOPIC')])

consumer2 = Consumer({
    'bootstrap.servers': os.environ.get('KAFKA_BOOTSTRAP_SERVER'),
    'security.protocol': os.environ.get('KAFKA_SECURITY_PROTOCOL'),
    'sasl.username': os.environ.get('KAFKA_USERNAME'),
    'sasl.password': os.environ.get('KAFKA_PASSWORD'),
    'sasl.mechanism': 'PLAIN',
    'group.id': os.environ.get('KAFKA_GROUP_2'),
    'auto.offset.reset': 'earliest'
}) 
consumer2.subscribe([os.environ.get('KAFKA_TOPIC_2')])

consumer3 = Consumer({
    'bootstrap.servers': os.environ.get('KAFKA_BOOTSTRAP_SERVER'),
    'security.protocol': os.environ.get('KAFKA_SECURITY_PROTOCOL'),
    'sasl.username': os.environ.get('KAFKA_USERNAME'),
    'sasl.password': os.environ.get('KAFKA_PASSWORD'),
    'sasl.mechanism': 'PLAIN',
    'group.id': os.environ.get('KAFKA_GROUP_3'),
    'auto.offset.reset': 'earliest'
}) 
consumer3.subscribe([os.environ.get('KAFKA_TOPIC_3')])

def process_msg1(message):
    print("Processing msg1:", message)
    try:
        user_id = message['id']
        # Create a cart for the user with the user_id
        cart, created = Cart.objects.get_or_create(user=user_id, defaults={'total_items': 0})
        if created:
            cart.save()
    except Exception as e:
        print(f"Error processing msg1: {str(e)}")
        print(traceback.format_exc())

def process_msg2(message):
    print("Processing msg2:", message)
    try:
        course_id = message['id']
        seller_id = message['seller_id']

        # Get the cart items for the deleted course and seller
        cart_items = CartItem.objects.filter(course=course_id, cart__user=seller_id)

        # Delete the cart items
        cart_items.delete()
    except Exception as e:
        print(f"Error processing msg2: {str(e)}")
        print(traceback.format_exc())


def process_msg3(message, key):
    print("Processing msg3:", message)
    try:
        user_id = message['user_id']

        if key == b'product_bought':
            product_id = message['product_id']
            CartItem.objects.filter(
                Q(cart__user=user_id),
                Q(product=product_id)
            ).delete()

        if key == b'course_bought':
            course_id = message['course_id']
            CartItem.objects.filter(
                Q(cart__user=user_id),
                Q(course=course_id)
            ).delete()
    except Exception as e:
        print(f"Error processing msg3: {str(e)}")
        print(traceback.format_exc())


while True:
    msg1 = consumer1.poll(1.0)
    msg2 = consumer2.poll(1.0)
    msg3 = consumer3.poll(1.0)

    if msg1 is not None and not msg1.error():
        topic1 = msg1.topic()
        value1 = msg1.value()

        if topic1 == os.environ.get('KAFKA_TOPIC') and msg1.key() == b'create_user':
            user_data = json.loads(value1)
            process_msg1(user_data)

    if msg2 is not None and not msg2.error():
        topic2 = msg2.topic()
        value2 = msg2.value()

        if topic2 == os.environ.get('KAFKA_TOPIC_2'):
            message = json.loads(value2)
            process_msg2(message)

    if msg3 is not None and not msg3.error():
        topic3 = msg3.topic()
        value3 = msg3.value()

        if topic3 == os.environ.get('KAFKA_TOPIC_3'):
            message = json.loads(value3)
            process_msg3(message, msg3.key())

consumer1.close()
consumer2.close()
consumer3.close()