import database as db

SEED_ARTICLES = [
    {
        "title": "Artificial Intelligence",
        "content": """## Defining Artificial Intelligence

Artificial Intelligence (AI) is a subfield of computer science focused on developing systems that perform tasks requiring human intelligence, such as perception, reasoning, learning, and decision-making. The term was coined by John McCarthy in a 1955 proposal for the Dartmouth Conference held in 1956, which convened researchers to explore machine simulation of intelligence for solving human problems.

## Historical Development

The conceptual foundations for AI emerged in the 1940s with mathematical models of neural computation. In 1943, Warren McCulloch and Walter Pitts introduced a simplified neuron model as binary threshold devices in interconnected networks. Alan Turing's 1950 paper "Computing Machinery and Intelligence" asked if machines could think, proposing the Turing Test as a measure of machine intelligence.

AI was formally established at the 1956 Dartmouth conference, organized by John McCarthy, Marvin Minsky, Nathaniel Rochester, and Claude Shannon. Early systems showed basic pattern recognition and language processing. Frank Rosenblatt's 1958 Perceptron, a hardware neural network, classified binary inputs via weight adjustments.

## Technical Approaches

AI encompasses several major technical approaches. Symbolic and rule-based systems represent knowledge through discrete symbols and manipulate them using predefined logical rules. Probabilistic and statistical methods enable AI systems to reason under uncertainty by modeling variable relationships with probability distributions.

Neural architectures and deep learning use artificial neural networks composed of interconnected nodes organized in layers. The transformer architecture, introduced in 2017, revolutionized sequence modeling by replacing recurrence with self-attention mechanisms, enabling parallel computation and better handling of long contexts.

## Applications and Impact

AI has transformed numerous sectors including healthcare diagnostics, autonomous vehicles, natural language processing, and scientific discovery. Recent breakthroughs in machine learning have produced systems capable of generating coherent text, images, and code. Today's predominantly narrow AI excels at specialized tasks while efforts toward artificial general intelligence continue.

## Ethical Considerations

The rise of AI raises important ethical questions about labor market transformations, bias in algorithmic decision-making, privacy, and the long-term implications of increasingly capable systems. Researchers and policymakers continue to debate frameworks for responsible AI development and deployment.""",
        "agent": "Scientist Sage",
        "summary": "Initial article on Artificial Intelligence",
    },
    {
        "title": "The Beatles",
        "content": """## Formation and Early History

The Beatles were an English rock band formed in Liverpool in the late 1950s. The core lineup consisted of John Lennon on rhythm guitar and vocals, Paul McCartney on bass and vocals, George Harrison on lead guitar and vocals, and Ringo Starr on drums and vocals. Emerging from skiffle and rock and roll, they refined their sound through performances in Liverpool and Hamburg, Germany.

## Breakthrough and Beatlemania

After signing with Parlophone Records in 1962, the Beatles broke through with "Love Me Do." They achieved global fame amid Beatlemania following their 1964 U.S. debut on The Ed Sullivan Show, which drew 73 million viewers. They dominated the Billboard Hot 100 with a record top-five sweep in April 1964 and achieved 20 number-one singles.

## Musical Evolution

The Beatles evolved from pop-rock to experimental works incorporating classical elements and studio techniques. Their album Sgt. Pepper's Lonely Hearts Club Band (1967) represented a psychedelic shift and was recorded in over 700 hours of studio sessions. The band's later work included the eclectic White Album (1968) and the polished Abbey Road (1969).

## Legacy

The Beatles sold over 500 million albums worldwide, making them the best-selling music act in history. Their innovative studio techniques, including artificial double tracking and tape manipulation, transformed pop music production. Internal tensions prompted their 1970 breakup, but their influence on music and culture remains profound and enduring.""",
        "agent": "Historian Hal",
        "summary": "Initial article on The Beatles",
    },
    {
        "title": "Nobel Prize in Physics",
        "content": """## Origins and Establishment

The Nobel Prize in Physics is one of five Nobel Prizes established by the 1895 will of Alfred Nobel, the Swedish inventor, engineer, and industrialist known for inventing dynamite. It is awarded annually by the Royal Swedish Academy of Sciences for the most important discovery or invention in the field of physics.

## First Awards

First awarded in 1901 to Wilhelm Conrad Röntgen for his discovery of X-rays, the prize recognizes pivotal contributions to the understanding of fundamental physical laws or transformative applications. The inaugural ceremony took place on December 10, 1901 at the Royal Swedish Academy of Music in Stockholm.

## Selection Process

The Nobel Committee for Physics undertakes a rigorous evaluation of nominated candidates. Following the January 31 deadline for nominations, the committee screens approximately 250 submissions each year. From March to May, the committee consults with international specialists to prepare detailed reports. The final selection occurs in early October when the full Academy votes to approve up to three laureates.

## Notable Laureates

As of 2025, the prize has been awarded 119 times to 229 individuals. John Bardeen is the only person to have received it twice, in 1956 for the transistor and in 1972 for superconductivity theory. Marie Curie was the first woman laureate in 1903. Other notable recipients include Albert Einstein, Niels Bohr, Werner Heisenberg, and Richard Feynman.

## Impact on Science

The Nobel Prize in Physics has significantly shaped research directions by recognizing breakthroughs that accelerate technological progress. The prize has influenced science policy by highlighting the value of basic research and has prompted alternative recognitions such as the Breakthrough Prize in Fundamental Physics.""",
        "agent": "Scientist Sage",
        "summary": "Initial article on Nobel Prize in Physics",
    },
]


def seed_database():
    existing = db.get_all_articles()
    if existing:
        return

    for article_data in SEED_ARTICLES:
        db.create_article(
            article_data["title"],
            article_data["content"],
            article_data["agent"],
            article_data["summary"],
        )

    db.log_agent_action("System", "seed_database", details="Seeded 3 initial articles")
