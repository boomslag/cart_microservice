import json, os, django
from confluent_kafka import Consumer

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "core.settings")
django.setup()

from django.apps import apps

Cart = apps.get_model('cart', 'Cart')
CartItem = apps.get_model('cart', 'CartItem')

consumer1 = Consumer({
    'bootstrap.servers': os.environ.get('KAFKA_BOOTSTRAP_SERVER'),
    'security.protocol': 'SASL_SSL',
    'sasl.username': os.environ.get('KAFKA_USERNAME'),
    'sasl.password': os.environ.get('KAFKA_PASSWORD'),
    'sasl.mechanism': 'PLAIN',
    'group.id': 'auth_group_cart',
    'auto.offset.reset': 'earliest'
})
consumer1.subscribe(['user_registered'])

consumer2 = Consumer({
    'bootstrap.servers': os.environ.get('KAFKA_BOOTSTRAP_SERVER'),
    'security.protocol': 'SASL_SSL',
    'sasl.username': os.environ.get('KAFKA_USERNAME'),
    'sasl.password': os.environ.get('KAFKA_PASSWORD'),
    'sasl.mechanism': 'PLAIN',
    'group.id': 'course_deleted',
    'auto.offset.reset': 'earliest'
})
consumer2.subscribe(['course_deleted'])

while True:
    msg1 = consumer1.poll(1.0)
    msg2 = consumer2.poll(1.0)

    if msg1 is not None and not msg1.error():
        topic1 = msg1.topic()
        value1 = msg1.value()

        if topic1 == 'user_registered':
            if msg1.key() == b'create_user':
                user_data = json.loads(value1)
                user_id = user_data['id']
                # create a cart for the user with the user_id
                cart, created = Cart.objects.get_or_create(user=user_id, defaults={'total_items': 0})
                if created:
                    cart.save()
                pass

    if msg2 is not None and not msg2.error():
        topic2 = msg2.topic()
        value2 = msg2.value()

        if topic2 == 'course_deleted':
            message = json.loads(value2)
            course_id = message['id']
            seller_id = message['seller_id']

            # Get the cart items for the deleted course and seller
            cart_items = CartItem.objects.filter(course=course_id, cart__user=seller_id)

            # Delete the cart items
            cart_items.delete()

consumer.close()